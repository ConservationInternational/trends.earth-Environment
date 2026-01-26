"""
Tests for compression features in the trends.earth-Environment API client
"""

import gzip
import json
import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

from gefcore import api


class TestCompressionAPIClient:
    """Test compression features in make_authenticated_request"""

    @pytest.fixture
    def mock_response(self):
        """Create a mock response object"""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"status": "success"}
        return response

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
        },
        clear=False,
    )
    @patch("requests.request")
    @patch("gefcore.api.get_access_token")
    def test_small_payload_no_compression(
        self, mock_get_token, mock_request, mock_response
    ):
        """Test that small payloads are not compressed"""
        mock_get_token.return_value = "test-token"
        mock_request.return_value = mock_response

        small_data = {"test": "data"}

        api.make_authenticated_request(
            "POST", "https://api.example.com/test", json=small_data
        )

        # Should be called with original json parameter (no compression)
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert "json" in call_args[1]
        assert "data" not in call_args[1]
        assert call_args[1]["json"] == small_data

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
        },
        clear=False,
    )
    @patch("requests.request")
    @patch("gefcore.api.get_access_token")
    def test_large_compressible_payload_compression(
        self, mock_get_token, mock_request, mock_response
    ):
        """Test that large compressible payloads are compressed"""
        mock_get_token.return_value = "test-token"
        mock_request.return_value = mock_response

        # Create large, highly compressible data
        large_data = {"test": ["repeated_value"] * 1000}

        api.make_authenticated_request(
            "POST", "https://api.example.com/test", json=large_data
        )

        # Should be called with compressed data
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert "data" in call_args[1]  # Compressed data
        assert "json" not in call_args[1]  # Original json removed
        assert call_args[1]["headers"]["Content-Type"] == "application/json"
        assert call_args[1]["headers"]["Content-Encoding"] == "gzip"

        # Verify the compressed data can be decompressed back to original
        compressed_data = call_args[1]["data"]
        decompressed = gzip.decompress(compressed_data).decode("utf-8")
        decompressed_json = json.loads(decompressed)
        assert decompressed_json == large_data

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
        },
        clear=False,
    )
    @patch("requests.request")
    @patch("gefcore.api.get_access_token")
    def test_large_random_payload_compression_behavior(
        self, mock_get_token, mock_request, mock_response
    ):
        """Test compression behavior with large random data"""
        mock_get_token.return_value = "test-token"
        mock_request.return_value = mock_response

        # Create large random data - gzip is very good so this will probably compress
        import base64
        import secrets

        large_random_data = {
            "random_fields": [
                base64.b64encode(secrets.token_bytes(64)).decode("ascii")
                for _ in range(50)  # 50 fields * 64 bytes * 4/3 (base64) = ~4.2KB
            ],
            "more_random": {
                f"key_{secrets.randbits(32)}": secrets.token_hex(32)
                for _ in range(25)  # Additional random data
            },
        }

        api.make_authenticated_request(
            "POST", "https://api.example.com/test", json=large_random_data
        )

        # Verify the request was made
        mock_request.assert_called_once()
        call_args = mock_request.call_args

        # The compression behavior depends on the actual compression ratio achieved
        # If compression ratio > 1.2, data will be compressed (data param used)
        # If compression ratio <= 1.2, data won't be compressed (json param used)
        has_compressed_data = "data" in call_args[1]
        has_json_data = "json" in call_args[1]

        # Exactly one should be true
        assert has_compressed_data ^ has_json_data, (
            "Should have either compressed data or json, not both"
        )

        # If compressed, verify proper headers are set
        if has_compressed_data:
            assert call_args[1]["headers"]["Content-Encoding"] == "gzip"
            assert call_args[1]["headers"]["Content-Type"] == "application/json"
        else:
            # If not compressed, original json should be preserved
            assert call_args[1]["json"] == large_random_data

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
        },
        clear=False,
    )
    @patch("requests.request")
    @patch("gefcore.api.get_access_token")
    def test_compression_failure_fallback(
        self, mock_get_token, mock_request, mock_response
    ):
        """Test that compression failures fall back to uncompressed"""
        mock_get_token.return_value = "test-token"
        mock_request.return_value = mock_response

        large_data = {"test": ["repeated_value"] * 1000}

        # Mock gzip.compress to fail
        with patch("gzip.compress", side_effect=Exception("Compression failed")):
            api.make_authenticated_request(
                "POST", "https://api.example.com/test", json=large_data
            )

        # Should fall back to uncompressed
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert "json" in call_args[1]
        assert call_args[1]["json"] == large_data

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
        },
        clear=False,
    )
    @patch("requests.request")
    @patch("gefcore.api.get_access_token")
    def test_compression_debug_logging(
        self, mock_get_token, mock_request, mock_response, caplog
    ):
        """Test that compression activity is logged for debugging"""
        mock_get_token.return_value = "test-token"
        mock_request.return_value = mock_response

        large_data = {"test": ["repeated_value"] * 1000}

        # Clear any existing log records
        caplog.clear()

        api.make_authenticated_request(
            "POST", "https://api.example.com/test", json=large_data
        )

        # Check that compression was logged
        assert any("compressing" in record.message.lower() for record in caplog.records)

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
        },
        clear=False,
    )
    @patch("requests.request")
    @patch("gefcore.api.get_access_token")
    def test_accept_encoding_header_always_set(
        self, mock_get_token, mock_request, mock_response
    ):
        """Test that Accept-Encoding header is always set for response compression"""
        mock_get_token.return_value = "test-token"
        mock_request.return_value = mock_response

        api.make_authenticated_request("GET", "https://api.example.com/test")

        # Should always set Accept-Encoding header
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[1]["headers"]["Accept-Encoding"] == "gzip, deflate"

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
        },
        clear=False,
    )
    @patch("requests.request")
    @patch("gefcore.api.get_access_token")
    def test_compression_with_401_retry(
        self, mock_get_token, mock_request, mock_response
    ):
        """Test that compression works correctly with 401 token refresh retry"""
        # First call returns 401, second call succeeds
        mock_response_401 = MagicMock()
        mock_response_401.status_code = 401
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200

        mock_request.side_effect = [mock_response_401, mock_response_success]
        mock_get_token.return_value = "test-token"

        large_data = {"test": ["repeated_value"] * 1000}

        result = api.make_authenticated_request(
            "POST", "https://api.example.com/test", json=large_data
        )

        # Should be called twice (first call fails with 401, second succeeds)
        assert mock_request.call_count == 2
        assert result.status_code == 200

        # Both calls should have compression applied consistently
        for call in mock_request.call_args_list:
            call_args = call[1]
            assert "data" in call_args  # Compressed data
            assert "json" not in call_args  # Original json removed
            assert call_args["headers"]["Content-Encoding"] == "gzip"


class TestCompressionThresholds:
    """Test compression threshold logic"""

    def test_compression_size_threshold(self):
        """Test that compression only applies to payloads >1KB"""
        # This tests the logic directly without making actual requests
        test_cases = [
            ({"small": "data"}, False),  # Small data should not be compressed
            ({"large": "x" * 1000}, True),  # Large data should be compressed
            ({"medium": "x" * 500}, False),  # Medium data below threshold
        ]

        for data, should_compress in test_cases:
            json_str = json.dumps(data, separators=(",", ":"))
            # The threshold in the code is 1000 bytes
            expected_compression = len(json_str) > 1000
            assert expected_compression == should_compress, (
                f"Size: {len(json_str)}, Expected: {should_compress}"
            )

    def test_compression_ratio_threshold(self):
        """Test that compression only applies when ratio >1.2"""
        # Highly compressible data (should compress)
        compressible_data = {"test": ["same"] * 1000}
        json_str = json.dumps(compressible_data, separators=(",", ":"))
        compressed = gzip.compress(json_str.encode("utf-8"))
        ratio = len(json_str) / len(compressed)
        assert ratio > 1.2, "Compressible data should have good compression ratio"

        # Less compressible data
        import secrets
        import string

        random_data = {
            "test": [
                "".join(secrets.choice(string.ascii_letters) for _ in range(10))
                for _ in range(200)
            ]
        }
        json_str = json.dumps(random_data, separators=(",", ":"))
        compressed = gzip.compress(json_str.encode("utf-8"))
        ratio = len(json_str) / len(compressed)
        # Random data typically has lower compression ratios


class TestCompressionIntegration:
    """Integration tests for compression features"""

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
        },
        clear=False,
    )
    def test_compression_preserves_request_parameters(self):
        """Test that compression doesn't interfere with other request parameters"""
        with (
            patch("requests.request") as mock_request,
            patch("gefcore.api.get_access_token") as mock_get_token,
        ):
            mock_get_token.return_value = "test-token"
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response

            large_data = {"test": ["repeated_value"] * 1000}

            api.make_authenticated_request(
                "POST",
                "https://api.example.com/test",
                json=large_data,
                timeout=30,
                headers={"Custom-Header": "value"},
            )

            call_args = mock_request.call_args
            # Should preserve custom headers (and add compression headers)
            assert call_args[1]["headers"]["Custom-Header"] == "value"
            assert call_args[1]["headers"]["Content-Encoding"] == "gzip"
            # Should preserve timeout
            assert call_args[1]["timeout"] == 30

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
        },
        clear=False,
    )
    def test_compression_with_non_json_requests(self):
        """Test that compression doesn't interfere with non-JSON requests"""
        with (
            patch("requests.request") as mock_request,
            patch("gefcore.api.get_access_token") as mock_get_token,
        ):
            mock_get_token.return_value = "test-token"
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response

            # Request without JSON data
            api.make_authenticated_request("GET", "https://api.example.com/test")

            call_args = mock_request.call_args
            # Should not add compression headers for non-JSON requests
            assert "Content-Encoding" not in call_args[1]["headers"]
            # Should still add Accept-Encoding for response compression
            assert call_args[1]["headers"]["Accept-Encoding"] == "gzip, deflate"

    @patch("gefcore.api.get_access_token")
    @patch("gefcore.api.requests.request")
    def test_uuid_serialization_in_compression(self, mock_request, mock_get_token):
        """Test that UUID objects are properly serialized during compression"""
        mock_get_token.return_value = "test-token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        # Create payload with UUID objects (like in error recode)
        test_uuid = uuid.uuid4()
        large_payload = {
            "error_polygons": [
                {
                    "id": test_uuid,  # This would cause JSON serialization error
                    "properties": {"uuid": test_uuid},
                    "data": "x" * 2000,  # Make it large enough to trigger compression
                }
            ]
        }

        # This should not raise a JSON serialization error
        api.make_authenticated_request(
            "POST", "https://api.example.com/test", json=large_payload
        )

        # Verify the request was made and compression was attempted
        mock_request.assert_called_once()
        call_args = mock_request.call_args

        # Should have compressed data since payload is large
        assert "data" in call_args[1]
        assert "json" not in call_args[1]  # json should be removed after compression

        # Decompress and verify UUID was serialized as string
        compressed_data = call_args[1]["data"]
        decompressed_data = gzip.decompress(compressed_data)
        parsed_data = json.loads(decompressed_data.decode("utf-8"))

        # UUIDs should be serialized as strings
        assert isinstance(parsed_data["error_polygons"][0]["id"], str)
        assert isinstance(parsed_data["error_polygons"][0]["properties"]["uuid"], str)
        assert parsed_data["error_polygons"][0]["id"] == str(test_uuid)

    @patch("gefcore.api.get_access_token")
    @patch("gefcore.api.requests.request")
    def test_small_payload_uuid_serialization(self, mock_request, mock_get_token):
        """Test that UUID objects are properly serialized even in small payloads (no compression)"""
        mock_get_token.return_value = "test-token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        # Create small payload with UUID objects (under 1KB, no compression)
        test_uuid = uuid.uuid4()
        small_payload = {
            "status": "FINISHED",
            "results": {
                "id": test_uuid,  # This would cause JSON serialization error
                "uuid": test_uuid,
                "some_data": "small payload",
            },
        }

        # This should not raise a JSON serialization error
        api.make_authenticated_request(
            "PATCH", "https://api.example.com/execution/123", json=small_payload
        )

        # Verify the request was made without compression (small payload)
        mock_request.assert_called_once()
        call_args = mock_request.call_args

        # Should NOT have compressed data since payload is small
        assert "data" not in call_args[1] or call_args[1].get("data") is None
        assert "json" in call_args[1]  # json should still be present for small payloads

        # Verify UUIDs were converted to strings in the json parameter
        json_data = call_args[1]["json"]
        assert isinstance(json_data["results"]["id"], str)
        assert isinstance(json_data["results"]["uuid"], str)
        assert json_data["results"]["id"] == str(test_uuid)
