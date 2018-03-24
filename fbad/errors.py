"""
Error and Exceptions.
"""

class PasswordRequired(Exception):
    """
    Exception raised when a Password is required but None specified.
    """
    pass


class InvalidPassword(Exception):
    """
    Exception raised when the server rejected the password.
    """
    pass
