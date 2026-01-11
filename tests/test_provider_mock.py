import pytest
import httpx
from unittest.mock import MagicMock, patch
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
from laptop_agents.resilience import (
    TransientProviderError,
    RateLimitProviderError,
    CircuitBreakerOpenError
)

@pytest.fixture
def provider():
    return BitunixFuturesProvider(
        symbol="BTCUSDT",
        api_key="test_key",
        secret_key="test_secret"
    )

def test_fetch_instrument_info_success(provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 0,
        "data": [
            {
                "symbol": "BTCUSDT",
                "tickSize": "0.1",
                "lotSize": "0.001",
                "minQty": "0.001",
                "maxQty": "100.0"
            }
        ]
    }
    
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    
    with patch("httpx.Client", return_value=mock_client):
        info = provider.fetch_instrument_info()
        assert info["tickSize"] == 0.1
        assert info["lotSize"] == 0.001

def test_retry_on_transient_error(provider):
    # First two calls timeout, third succeeds
    timeout_error = httpx.TimeoutException("Timeout")
    
    success_response = MagicMock()
    success_response.status_code = 200
    success_response.json.return_value = {"code": 0, "data": []}
    
    mock_client = MagicMock()
    mock_client.get.side_effect = [timeout_error, timeout_error, success_response]
    mock_client.__enter__.return_value = mock_client
    
    with patch("httpx.Client", return_value=mock_client):
        provider.trading_pairs()
        assert mock_client.get.call_count == 3

def test_circuit_breaker_opens_on_repeated_errors(provider):
    # Mocking a repeated rate limit error
    rate_limit_response = MagicMock()
    rate_limit_response.status_code = 429
    # Simulate the response raising for status
    rate_limit_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Rate limit", request=MagicMock(), response=rate_limit_response
    )
    
    mock_client = MagicMock()
    mock_client.get.return_value = rate_limit_response
    mock_client.__enter__.return_value = mock_client
    
    with patch("httpx.Client", return_value=mock_client):
        # The circuit breaker is configured for 3 failures.
        # Each attempted call to _call_exchange will trigger the retry policy.
        # Since every attempt fails, it will exhaust 3 retries and then record ONE failure in the circuit breaker.
        # We need to do this 3 times to open the circuit.
        
        for _ in range(3):
            with pytest.raises(RateLimitProviderError):
                provider.trading_pairs()
        
        # 4th call should raise CircuitBreakerOpenError immediately WITHOUT calling get()
        with pytest.raises(CircuitBreakerOpenError):
            provider.trading_pairs()
        
        # Total calls to get() should be 3 (calls) * 3 (retries) = 9
        assert mock_client.get.call_count == 9
