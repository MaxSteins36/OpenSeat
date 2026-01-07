import requests
import os
from bs4 import BeautifulSoup
import sys
from dotenv import load_dotenv

# --- Configuration ---
# For local testing, it loads from .env. In GitHub Actions, it loads from Secrets.
load_dotenv() 

TERM_CODE = "202610" 
COURSE_SUBJECT_CODE = "BUS106"

PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_API_TOKEN = os.getenv('PUSHOVER_API_TOKEN')

# --- Main Application Logic ---

def send_pushover_notification(title, message, is_high_priority=False):
    """Sends a notification via the Pushover API."""
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("FATAL: Pushover credentials not set. Cannot send notification.")
        return

    url = "https://api.pushover.net/1/messages.json"
    payload = {
        'token': PUSHOVER_API_TOKEN,
        'user': PUSHOVER_USER_KEY,
        'title': title,
        'message': message,
        'html': 1 
    }
    
    # Set priority to 1 (high) if a seat is found or an error occurs
    if is_high_priority:
        payload['priority'] = 1
        payload['sound'] = 'persistent' # A more urgent sound

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        print(f"Successfully sent notification: '{title}'")
    except requests.exceptions.RequestException as e:
        print(f"Error sending Pushover notification: {e}")

def check_class_availability():
    """Main function to check UCR class availability and send notifications."""
    print(f"Starting check for {COURSE_SUBJECT_CODE} (Term: {TERM_CODE})...")
    SEARCH_PAGE_URL = "https://registrationssb.ucr.edu/StudentRegistrationSsb/ssb/classSearch/classSearch"
    TERM_SELECT_URL = "https://registrationssb.ucr.edu/StudentRegistrationSsb/ssb/term/search?mode=search"
    API_URL = "https://registrationssb.ucr.edu/StudentRegistrationSsb/ssb/searchResults/searchResults"

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    })

    try:
        # Step 1: Initialize session
        session.get(SEARCH_PAGE_URL, timeout=15).raise_for_status()

        # Step 2: Select the term
        session.post(TERM_SELECT_URL, data={'term': TERM_CODE}).raise_for_status()

        # Step 3: Query for course data
        api_params = {'txt_subjectcoursecombo': COURSE_SUBJECT_CODE, 'txt_term': TERM_CODE, 'pageMaxSize': 50}
        api_response = session.get(API_URL, params=api_params, timeout=15)
        api_response.raise_for_status()
        data = api_response.json()

        if not data.get('success') or 'data' not in data or data['totalCount'] == 0:
            raise ValueError("API returned 0 sections. The Term Code may be invalid or the API may have changed.")

        open_and_wanted_sections = []
        for section in data['data']:
            if section['seatsAvailable'] > 0:
                is_excluded = False
                if section['scheduleTypeDescription'] == 'Discussion':
                    for meeting in section['meetingsFaculty']:
                        mt = meeting['meetingTime']
                        if mt.get('friday') and mt.get('beginTime') in ['0800', '0900']:
                            is_excluded = True
                            break
                if not is_excluded:
                    open_and_wanted_sections.append(section)
        
        if open_and_wanted_sections:
            print(f"SUCCESS: Found {len(open_and_wanted_sections)} open sections!")
            message_body = ""
            for section in open_and_wanted_sections:
                message_body += (
                    f"<b>CRN {section['courseReferenceNumber']} ({section['scheduleTypeDescription']})</b><br>"
                    f"Seats: <b>{section['seatsAvailable']}</b>/{section['maximumEnrollment']}<br>"
                    f"Instructor: {section['faculty'][0]['displayName']}<br>"
                )
                # Add meeting times for clarity
                for meeting in section['meetingsFaculty']:
                    mt = meeting['meetingTime']
                    days = "".join([d[0] for d in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'] if mt.get(d)])
                    message_body += f"{days} {mt.get('beginTime')}-{mt.get('endTime')} in {mt.get('buildingDescription')} {mt.get('room')}<br>"
                message_body += "<br>" # Add space between sections

            send_pushover_notification(f"Seat Found for {COURSE_SUBJECT_CODE}!", message_body, is_high_priority=True)
        else:
            print("Check complete. No open seats found that match your criteria.")

    except (requests.exceptions.RequestException, ValueError) as e:
        error_message = f"The UCR class checker failed with an error: {e}"
        print(error_message)
        send_pushover_notification("UCR Checker Failure", error_message, is_high_priority=True)
        sys.exit(1) # Exit with error code

if __name__ == "__main__":
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("FATAL: PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN environment variables must be set.")
        sys.exit(1)
    check_class_availability()