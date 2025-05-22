from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re
from fastapi import HTTPException
import time

class SpamHandler:
    def __init__(self):
        # Store submission attempts with timestamps
        self.submission_history: Dict[str, List[datetime]] = {}
        # Rate limiting settings
        self.max_submissions_per_hour = 3
        self.max_submissions_per_day = 10
        self.suspicious_patterns = [
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',  # URLs
            r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}',  # Multiple emails
            r'(?i)(viagra|cialis|levitra|pharmacy|drugs|medication)',  # Common spam keywords
            r'(?i)(buy|sell|discount|offer|deal|cheap|price)',  # Commercial keywords
        ]
        self.suspicious_keywords = [
            'viagra', 'cialis', 'pharmacy', 'drugs', 'medication',
            'buy', 'sell', 'discount', 'offer', 'deal', 'cheap',
            'lottery', 'winner', 'inheritance', 'bank', 'transfer'
        ]

    def is_spam(self, name: str, email: str, phone: Optional[str], about_case: str) -> bool:
        """
        Check if the submission appears to be spam based on various criteria.
        """
        # Check for suspicious patterns in the message
        for pattern in self.suspicious_patterns:
            if re.search(pattern, about_case):
                return True

        # Check for suspicious keywords
        about_case_lower = about_case.lower()
        for keyword in self.suspicious_keywords:
            if keyword in about_case_lower:
                return True

        # Check for excessive capitalization
        if sum(1 for c in about_case if c.isupper()) / len(about_case) > 0.7:
            return True

        # Check for repetitive content
        words = about_case.split()
        if len(words) > 10:
            word_freq = {}
            for word in words:
                word_freq[word] = word_freq.get(word, 0) + 1
            if max(word_freq.values()) > len(words) * 0.3:  # If any word appears more than 30% of the time
                return True

        return False

    def check_rate_limit(self, email: str) -> bool:
        """
        Check if the submission exceeds rate limits.
        """
        current_time = datetime.now()
        
        # Initialize submission history for this email if not exists
        if email not in self.submission_history:
            self.submission_history[email] = []

        # Clean up old submissions
        self.submission_history[email] = [
            timestamp for timestamp in self.submission_history[email]
            if current_time - timestamp < timedelta(days=1)
        ]

        # Check hourly limit
        recent_submissions = [
            timestamp for timestamp in self.submission_history[email]
            if current_time - timestamp < timedelta(hours=1)
        ]
        if len(recent_submissions) >= self.max_submissions_per_hour:
            return False

        # Check daily limit
        if len(self.submission_history[email]) >= self.max_submissions_per_day:
            return False

        # Add new submission
        self.submission_history[email].append(current_time)
        return True

    def validate_submission(self, name: str, email: str, phone: Optional[str], about_case: str) -> None:
        """
        Validate a submission and raise appropriate exceptions if spam is detected.
        """
        # Check rate limits
        if not self.check_rate_limit(email):
            raise HTTPException(
                status_code=429,
                detail="Too many submissions. Please try again later."
            )

        # Check for spam
        if self.is_spam(name, email, phone, about_case):
            raise HTTPException(
                status_code=400,
                detail="Submission appears to be spam and has been rejected."
            )

# Create a global instance
spam_handler = SpamHandler() 