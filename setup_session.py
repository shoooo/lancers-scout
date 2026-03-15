"""
One-time headful login to complete Lancers 2FA and save the session.
Run this once:  python3 setup_session.py
After that, all other commands run headless using the saved session.
"""

from browser import LancersSession

print("Opening browser for Lancers login...")
print("Check your email for the verification code and enter it in the browser window.\n")

with LancersSession(headless=False) as session:
    session.login()
    print("\nSession saved. You can now run main.py in headless mode.")
