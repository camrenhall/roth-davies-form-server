import pytest
from fastapi import HTTPException
from spam_handler import SpamHandler
from datetime import datetime, timedelta
import time

@pytest.fixture
def spam_handler():
    return SpamHandler()

def test_normal_submission(spam_handler):
    """Test a normal, legitimate submission"""
    try:
        spam_handler.validate_submission(
            name="John Doe",
            email="john@example.com",
            phone="1234567890",
            about_case="I need legal help with my case."
        )
        assert True  # If no exception is raised, test passes
    except HTTPException:
        assert False  # Test fails if exception is raised

def test_spam_keywords(spam_handler):
    """Test submission with spam keywords"""
    with pytest.raises(HTTPException) as exc_info:
        spam_handler.validate_submission(
            name="John Doe",
            email="john@example.com",
            phone="1234567890",
            about_case="Buy cheap viagra online now!"
        )
    assert exc_info.value.status_code == 400
    assert "spam" in exc_info.value.detail.lower()

def test_url_spam(spam_handler):
    """Test submission containing URLs"""
    with pytest.raises(HTTPException) as exc_info:
        spam_handler.validate_submission(
            name="John Doe",
            email="john@example.com",
            phone="1234567890",
            about_case="Check out my website https://spam.com"
        )
    assert exc_info.value.status_code == 400

def test_excessive_capitalization(spam_handler):
    """Test submission with excessive capitalization"""
    with pytest.raises(HTTPException) as exc_info:
        spam_handler.validate_submission(
            name="John Doe",
            email="john@example.com",
            phone="1234567890",
            about_case="I NEED LEGAL HELP RIGHT NOW THIS IS URGENT PLEASE HELP ME"
        )
    assert exc_info.value.status_code == 400

def test_repetitive_content(spam_handler):
    """Test submission with repetitive content"""
    with pytest.raises(HTTPException) as exc_info:
        spam_handler.validate_submission(
            name="John Doe",
            email="john@example.com",
            phone="1234567890",
            about_case="help help help help help help help help help help help help help help help"
        )
    assert exc_info.value.status_code == 400

def test_rate_limiting(spam_handler):
    """Test rate limiting functionality"""
    email = "test@example.com"
    
    # Should allow first 3 submissions within an hour
    for _ in range(3):
        try:
            spam_handler.validate_submission(
                name="John Doe",
                email=email,
                phone="1234567890",
                about_case="Test submission"
            )
        except HTTPException:
            assert False  # Should not raise exception for first 3 submissions
    
    # Fourth submission within an hour should be blocked
    with pytest.raises(HTTPException) as exc_info:
        spam_handler.validate_submission(
            name="John Doe",
            email=email,
            phone="1234567890",
            about_case="Test submission"
        )
    assert exc_info.value.status_code == 429
    assert "too many submissions" in exc_info.value.detail.lower()

def test_daily_limit(spam_handler):
    """Test daily submission limit"""
    email = "daily@example.com"
    spam_handler.max_submissions_per_hour = 11  # Allow more per hour for this test

    # Should allow first 10 submissions
    for i in range(10):
        try:
            spam_handler.validate_submission(
                name="John Doe",
                email=email,
                phone="1234567890",
                about_case="Test submission"
            )
        except HTTPException as e:
            assert False, f"Unexpected exception on submission {i+1}: {str(e)}"

    # 11th submission should be blocked
    with pytest.raises(HTTPException) as exc_info:
        spam_handler.validate_submission(
            name="John Doe",
            email=email,
            phone="1234567890",
            about_case="Test submission"
        )
    assert exc_info.value.status_code == 429
    assert "too many submissions" in exc_info.value.detail.lower()

def test_multiple_emails(spam_handler):
    """Test submission with multiple email addresses in the message"""
    with pytest.raises(HTTPException) as exc_info:
        spam_handler.validate_submission(
            name="John Doe",
            email="john@example.com",
            phone="1234567890",
            about_case="Contact me at spam1@example.com or spam2@example.com"
        )
    assert exc_info.value.status_code == 400

if __name__ == "__main__":
    pytest.main(["-v", "test_spam_handler.py"]) 