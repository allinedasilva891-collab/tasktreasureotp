#!/usr/bin/env python3
"""
Simple OTP Bot using requests (NO BROWSER NEEDED)
- Render compatible (no system dependencies)
- Fast login and monitoring
- Direct HTTP requests
"""

import asyncio
import logging
import os
import re
import hashlib
import time
from datetime import datetime
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleRequestsOTPBot:
    def __init__(self):
        # Website credentials
        self.login_url = "http://94.23.120.156/ints/login"
        self.sms_url = "http://94.23.120.156/ints/client/SMSCDRStats"
        self.username = "Roni_dada"
        self.password = "Roni_dada"
        
        # Session for persistent cookies
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # State management
        self.logged_in = False
        self.processed_hashes = set()
        self.last_check_time = 0
        self.failure_count = 0
        self.max_hashes = 1000
        
        # Telegram bot for channel messages
        self.bot_token = os.getenv('BOT_TOKEN')
        self.channel_id = "-1002724043027"
        
        # Initialize number bot
        try:
            from telegram_number_bot import TelegramNumberBot
            self.number_bot = TelegramNumberBot()
            logger.info("✅ Number bot ready for user notifications")
        except Exception as e:
            logger.warning(f"⚠️ Number bot not available: {e}")
            self.number_bot = None
    
    def login_once(self) -> bool:
        """Login once using requests"""
        try:
            logger.info("🔐 Logging in with requests...")
            
            # Get login page first
            response = self.session.get(self.login_url, timeout=30)
            if response.status_code != 200:
                logger.error(f"❌ Login page failed: {response.status_code}")
                return False
            
            # Parse the page for form and captcha
            soup = BeautifulSoup(response.text, 'html.parser')
            logger.info(f"Login page title: {soup.title.string if soup.title else 'No title'}")
            
            # Find the login form
            form = soup.find('form')
            if not form:
                logger.error("❌ No form found on login page")
                return False
            
            # Get form action and method
            form_action = form.get('action', '')
            form_method = form.get('method', 'post').lower()
            logger.info(f"Form action: {form_action}, method: {form_method}")
            
            # Collect all form fields
            login_data = {}
            for input_field in form.find_all(['input', 'select', 'textarea']):
                field_name = input_field.get('name')
                field_type = input_field.get('type', 'text')
                field_value = input_field.get('value', '')
                
                if field_name:
                    login_data[field_name] = field_value
                    logger.info(f"Found form field: {field_name} = '{field_value}' (type: {field_type})")
            
            # Override with our credentials
            login_data['username'] = self.username
            login_data['password'] = self.password
            
            # Solve captcha - try multiple approaches
            captcha_answer = ""
            
            # Approach 1: Find label for captcha
            captcha_label = soup.find('label', {'for': 'capt'})
            if captcha_label:
                captcha_text = captcha_label.get_text()
                logger.info(f"Found captcha label: {captcha_text}")
                match = re.search(r'(\d+)\s*\+\s*(\d+)', captcha_text)
                if match:
                    captcha_answer = str(int(match.group(1)) + int(match.group(2)))
                    logger.info(f"✅ Captcha solved: {captcha_text} = {captcha_answer}")
            
            # Approach 2: Search entire page for captcha
            if not captcha_answer:
                page_text = response.text
                captcha_matches = re.findall(r'(\d+)\s*\+\s*(\d+)', page_text)
                if captcha_matches:
                    nums = captcha_matches[0]
                    captcha_answer = str(int(nums[0]) + int(nums[1]))
                    logger.info(f"✅ Captcha found in page: {nums[0]} + {nums[1]} = {captcha_answer}")
            
            if captcha_answer:
                login_data['capt'] = captcha_answer
            else:
                logger.warning("⚠️ No captcha found, proceeding without it")
            
            # Add common form headers
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': self.login_url,
                'Origin': 'http://94.23.120.156'
            }
            
            # Determine correct submit URL
            if form_action:
                if form_action.startswith('http'):
                    submit_url = form_action
                else:
                    # Relative URL - construct full URL
                    base_url = "http://94.23.120.156/ints/"
                    submit_url = base_url + form_action.lstrip('/')
            else:
                submit_url = self.login_url
            
            logger.info(f"Submitting to: {submit_url}")
            
            # Submit login
            login_response = self.session.post(
                submit_url, 
                data=login_data,
                headers=headers,
                timeout=30,
                allow_redirects=True
            )
            
            # Check if login successful
            logger.info(f"Login response URL: {login_response.url}")
            logger.info(f"Login response status: {login_response.status_code}")
            
            # Multiple success checks
            success_indicators = [
                "client" in login_response.url and "login" not in login_response.url,
                "SMSCDRStats" in login_response.text,
                "Dashboard" in login_response.text,
                "welcome" in login_response.text.lower(),
                "logout" in login_response.text.lower()
            ]
            
            if any(success_indicators):
                logger.info("✅ Login successful - found success indicator")
                self.logged_in = True
                return True
            else:
                # Check for specific error messages
                response_text = login_response.text.lower()
                if "captcha verification failed" in response_text:
                    logger.error("❌ Login failed - CAPTCHA verification failed")
                    logger.info("🔧 SOLUTION NEEDED: Website may have changed captcha system")
                elif "username/password invalid" in response_text:
                    logger.error("❌ Login failed - Invalid credentials")
                    logger.info("🔧 SOLUTION NEEDED: Please check username/password")
                elif "error" in response_text or "invalid" in response_text:
                    logger.error("❌ Login failed - error message detected")
                else:
                    logger.error(f"❌ Login failed - no success indicators found")
                    logger.info(f"Response preview: {login_response.text[:200]}...")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            return False
    
    def check_for_messages(self) -> List[Dict]:
        """Check for messages using AJAX endpoint with logout detection"""
        try:
            if not self.logged_in:
                return []
            
            # First check if we're still logged in by accessing SMS page
            check_response = self.session.get(self.sms_url, timeout=15)
            if check_response.status_code != 200:
                logger.warning(f"⚠️ SMS page failed: {check_response.status_code}")
                return []
            
            # 🔍 LOGOUT DETECTION: Check if URL changed (redirected to login)
            final_url = check_response.url
            if "login" in final_url.lower() or "signin" in final_url.lower():
                logger.warning(f"🔓 LOGOUT DETECTED! Redirected to: {final_url}")
                logger.info("🔄 Attempting automatic re-login...")
                self.logged_in = False
                
                # Attempt re-login
                if self.login_once():
                    logger.info("✅ Re-login successful, retrying message check...")
                    return self.check_for_messages()
                else:
                    logger.error("❌ Re-login failed")
                    return []
            
            # Check page title for logout detection
            soup = BeautifulSoup(check_response.text, 'html.parser')
            page_title = soup.find('title')
            if page_title and "login" in page_title.get_text().lower():
                logger.warning("🔓 LOGOUT DETECTED! On login page")
                logger.info("🔄 Attempting automatic re-login...")
                self.logged_in = False
                
                if self.login_once():
                    logger.info("✅ Re-login successful, retrying message check...")
                    return self.check_for_messages()
                else:
                    logger.error("❌ Re-login failed")
                    return []
            
            # 🚀 USE AJAX ENDPOINT FOR REAL DATA
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            
            ajax_url = "http://94.23.120.156/ints/client/res/data_smscdr.php"
            
            # DataTables headers for AJAX request
            headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': 'http://94.23.120.156/ints/client/SMSCDRStats',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            # AJAX parameters
            params = {
                'fdate1': f'{today} 00:00:00',
                'fdate2': f'{today} 23:59:59',
                'frange': '',
                'fnum': '',
                'fcli': '',
                'fgdate': '',
                'fgmonth': '',
                'fgrange': '',
                'fgnumber': '',
                'fgcli': '',
                'fg': '0',
                'draw': '1',
                'start': '0',
                'length': '100',
                'search[value]': '',
                'search[regex]': 'false',
                '_': str(int(datetime.now().timestamp() * 1000))
            }
            
            # Make AJAX request
            response = self.session.post(ajax_url, data=params, headers=headers, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"⚠️ AJAX request failed: {response.status_code}")
                return []
            
            # Parse JSON response
            try:
                data = response.json()
                sms_records = data.get('aaData', [])
                
                messages = []
                for record in sms_records:
                    if isinstance(record, list) and len(record) >= 5:
                        # Skip summary rows (like ['0,0,0,1', 0, 0, 0, 0, 0, 0])
                        if isinstance(record[0], str) and ',' in record[0]:
                            continue
                            
                        try:
                            timestamp = str(record[0])
                            service_range = str(record[1])  # Service description
                            number = str(record[2])
                            service = str(record[3])        # Service name (CLI column)
                            message = str(record[4])
                            
                            # Debug: Log CLI column value and message
                            logger.info(f"🔍 Service: '{service}' | Number: {number} | Message: {message[:50]}...")
                            
                            # Accept messages with digits (potential OTP)
                            if message and len(message) > 5:
                                # Check if message contains digits (potential OTP)
                                if any(char.isdigit() for char in message):
                                    messages.append({
                                        'timestamp': timestamp,
                                        'number': number,
                                        'service': service,
                                        'message': message,
                                        'service_range': service_range
                                    })
                        except Exception as parse_error:
                            logger.warning(f"⚠️ AJAX record parse error: {parse_error}")
                            continue
                
                logger.info(f"📊 Found {len(messages)} messages via AJAX")
                return messages
                
            except Exception as json_error:
                logger.error(f"❌ AJAX JSON parse error: {json_error}")
                return []
            
        except Exception as e:
            logger.error(f"❌ Message check error: {e}")
            self.failure_count += 1
            return []
    
    def extract_otp_data(self, message_data: Dict) -> Optional[Dict]:
        """Extract OTP from message"""
        try:
            message = message_data['message']
            
            # Find OTP code (4-8 digits)
            otp_patterns = [
                r'\b(\d{4,8})\b',
                r'code[:\s]+(\d{4,8})',
                r'verification[:\s]+(\d{4,8})',
                r'OTP[:\s]+(\d{4,8})'
            ]
            
            otp_code = None
            for pattern in otp_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    otp_code = match.group(1)
                    break
            
            if otp_code:
                return {
                    'otp_code': otp_code,
                    'service': message_data['service'],
                    'number': message_data['number'],
                    'message': message,
                    'timestamp': message_data['timestamp']
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ OTP extraction error: {e}")
            return None
    
    def get_message_hash(self, message: str) -> str:
        """Generate hash for message"""
        return hashlib.md5(message.encode()).hexdigest()[:16]
    
    async def send_to_channel_direct(self, message: str):
        """Send message directly to Telegram channel"""
        try:
            if not self.bot_token:
                logger.error("❌ No bot token available for channel sending")
                return False
                
            import telegram
            from telegram.constants import ParseMode
            
            bot = telegram.Bot(token=self.bot_token)
            
            # Try Markdown first, fallback to plain text if parsing fails
            try:
                await bot.send_message(
                    chat_id=self.channel_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info("📢 Message sent to channel with Markdown")
                return True
            except Exception as markdown_error:
                logger.warning(f"⚠️ Markdown failed: {markdown_error}")
                # Fallback to plain text
                try:
                    await bot.send_message(
                        chat_id=self.channel_id,
                        text=message
                    )
                    logger.info("📢 Message sent to channel as plain text")
                    return True
                except Exception as plain_error:
                    logger.error(f"❌ Plain text also failed: {plain_error}")
                    return False
            
        except Exception as e:
            logger.error(f"❌ Channel send error: {e}")
            return False

    def escape_markdown(self, text: str) -> str:
        """Escape special characters for Telegram Markdown"""
        if not text:
            return text
        # Escape special markdown characters
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    def get_country_info_from_number(self, phone_number: str) -> Dict[str, str]:
        """Get country name and flag based on phone number (same logic as original)"""
        country_codes = {
            # Major countries
            '1': {'name': 'USA/Canada', 'flag': '🇺🇸'},
            '7': {'name': 'Russia', 'flag': '🇷🇺'},
            '20': {'name': 'Egypt', 'flag': '🇪🇬'},
            '27': {'name': 'South Africa', 'flag': '🇿🇦'},
            '30': {'name': 'Greece', 'flag': '🇬🇷'},
            '31': {'name': 'Netherlands', 'flag': '🇳🇱'},
            '32': {'name': 'Belgium', 'flag': '🇧🇪'},
            '33': {'name': 'France', 'flag': '🇫🇷'},
            '34': {'name': 'Spain', 'flag': '🇪🇸'},
            '36': {'name': 'Hungary', 'flag': '🇭🇺'},
            '39': {'name': 'Italy', 'flag': '🇮🇹'},
            '40': {'name': 'Romania', 'flag': '🇷🇴'},
            '41': {'name': 'Switzerland', 'flag': '🇨🇭'},
            '43': {'name': 'Austria', 'flag': '🇦🇹'},
            '44': {'name': 'United Kingdom', 'flag': '🇬🇧'},
            '45': {'name': 'Denmark', 'flag': '🇩🇰'},
            '46': {'name': 'Sweden', 'flag': '🇸🇪'},
            '47': {'name': 'Norway', 'flag': '🇳🇴'},
            '48': {'name': 'Poland', 'flag': '🇵🇱'},
            '49': {'name': 'Germany', 'flag': '🇩🇪'},
            '51': {'name': 'Peru', 'flag': '🇵🇪'},
            '52': {'name': 'Mexico', 'flag': '🇲🇽'},
            '53': {'name': 'Cuba', 'flag': '🇨🇺'},
            '54': {'name': 'Argentina', 'flag': '🇦🇷'},
            '55': {'name': 'Brazil', 'flag': '🇧🇷'},
            '56': {'name': 'Chile', 'flag': '🇨🇱'},
            '57': {'name': 'Colombia', 'flag': '🇨🇴'},
            '58': {'name': 'Venezuela', 'flag': '🇻🇪'},
            '60': {'name': 'Malaysia', 'flag': '🇲🇾'},
            '61': {'name': 'Australia', 'flag': '🇦🇺'},
            '62': {'name': 'Indonesia', 'flag': '🇮🇩'},
            '63': {'name': 'Philippines', 'flag': '🇵🇭'},
            '64': {'name': 'New Zealand', 'flag': '🇳🇿'},
            '65': {'name': 'Singapore', 'flag': '🇸🇬'},
            '66': {'name': 'Thailand', 'flag': '🇹🇭'},
            '81': {'name': 'Japan', 'flag': '🇯🇵'},
            '82': {'name': 'South Korea', 'flag': '🇰🇷'},
            '84': {'name': 'Vietnam', 'flag': '🇻🇳'},
            '86': {'name': 'China', 'flag': '🇨🇳'},
            '90': {'name': 'Turkey', 'flag': '🇹🇷'},
            '91': {'name': 'India', 'flag': '🇮🇳'},
            '92': {'name': 'Pakistan', 'flag': '🇵🇰'},
            '93': {'name': 'Afghanistan', 'flag': '🇦🇫'},
            '94': {'name': 'Sri Lanka', 'flag': '🇱🇰'},
            '95': {'name': 'Myanmar', 'flag': '🇲🇲'},
            '98': {'name': 'Iran', 'flag': '🇮🇷'},
            '212': {'name': 'Morocco', 'flag': '🇲🇦'},
            '213': {'name': 'Algeria', 'flag': '🇩🇿'},
            '216': {'name': 'Tunisia', 'flag': '🇹🇳'},
            '218': {'name': 'Libya', 'flag': '🇱🇾'},
            '220': {'name': 'Gambia', 'flag': '🇬🇲'},
            '221': {'name': 'Senegal', 'flag': '🇸🇳'},
            '222': {'name': 'Mauritania', 'flag': '🇲🇷'},
            '223': {'name': 'Mali', 'flag': '🇲🇱'},
            '224': {'name': 'Guinea', 'flag': '🇬🇳'},
            '225': {'name': 'Ivory Coast', 'flag': '🇨🇮'},
            '226': {'name': 'Burkina Faso', 'flag': '🇧🇫'},
            '227': {'name': 'Niger', 'flag': '🇳🇪'},
            '228': {'name': 'Togo', 'flag': '🇹🇬'},
            '229': {'name': 'Benin', 'flag': '🇧🇯'},
            '230': {'name': 'Mauritius', 'flag': '🇲🇺'},
            '231': {'name': 'Liberia', 'flag': '🇱🇷'},
            '232': {'name': 'Sierra Leone', 'flag': '🇸🇱'},
            '233': {'name': 'Ghana', 'flag': '🇬🇭'},
            '234': {'name': 'Nigeria', 'flag': '🇳🇬'},
            '235': {'name': 'Chad', 'flag': '🇹🇩'},
            '236': {'name': 'Central African Republic', 'flag': '🇨🇫'},
            '237': {'name': 'Cameroon', 'flag': '🇨🇲'},
            '238': {'name': 'Cape Verde', 'flag': '🇨🇻'},
            '239': {'name': 'Sao Tome and Principe', 'flag': '🇸🇹'},
            '240': {'name': 'Equatorial Guinea', 'flag': '🇬🇶'},
            '241': {'name': 'Gabon', 'flag': '🇬🇦'},
            '242': {'name': 'Republic of the Congo', 'flag': '🇨🇬'},
            '243': {'name': 'Democratic Republic of the Congo', 'flag': '🇨🇩'},
            '244': {'name': 'Angola', 'flag': '🇦🇴'},
            '245': {'name': 'Guinea-Bissau', 'flag': '🇬🇼'},
            '246': {'name': 'British Indian Ocean Territory', 'flag': '🇮🇴'},
            '247': {'name': 'Ascension Island', 'flag': '🇦🇨'},
            '248': {'name': 'Seychelles', 'flag': '🇸🇨'},
            '249': {'name': 'Sudan', 'flag': '🇸🇩'},
            '250': {'name': 'Rwanda', 'flag': '🇷🇼'},
            '251': {'name': 'Ethiopia', 'flag': '🇪🇹'},
            '252': {'name': 'Somalia', 'flag': '🇸🇴'},
            '253': {'name': 'Djibouti', 'flag': '🇩🇯'},
            '254': {'name': 'Kenya', 'flag': '🇰🇪'},
            '255': {'name': 'Tanzania', 'flag': '🇹🇿'},
            '256': {'name': 'Uganda', 'flag': '🇺🇬'},
            '257': {'name': 'Burundi', 'flag': '🇧🇮'},
            '258': {'name': 'Mozambique', 'flag': '🇲🇿'},
            '260': {'name': 'Zambia', 'flag': '🇿🇲'},
            '261': {'name': 'Madagascar', 'flag': '🇲🇬'},
            '262': {'name': 'Reunion', 'flag': '🇷🇪'},
            '263': {'name': 'Zimbabwe', 'flag': '🇿🇼'},
            '264': {'name': 'Namibia', 'flag': '🇳🇦'},
            '265': {'name': 'Malawi', 'flag': '🇲🇼'},
            '266': {'name': 'Lesotho', 'flag': '🇱🇸'},
            '267': {'name': 'Botswana', 'flag': '🇧🇼'},
            '268': {'name': 'Swaziland', 'flag': '🇸🇿'},
            '269': {'name': 'Comoros', 'flag': '🇰🇲'},
            '290': {'name': 'Saint Helena', 'flag': '🇸🇭'},
            '291': {'name': 'Eritrea', 'flag': '🇪🇷'},
            '297': {'name': 'Aruba', 'flag': '🇦🇼'},
            '298': {'name': 'Faroe Islands', 'flag': '🇫🇴'},
            '299': {'name': 'Greenland', 'flag': '🇬🇱'},
            '350': {'name': 'Gibraltar', 'flag': '🇬🇮'},
            '351': {'name': 'Portugal', 'flag': '🇵🇹'},
            '352': {'name': 'Luxembourg', 'flag': '🇱🇺'},
            '353': {'name': 'Ireland', 'flag': '🇮🇪'},
            '354': {'name': 'Iceland', 'flag': '🇮🇸'},
            '355': {'name': 'Albania', 'flag': '🇦🇱'},
            '356': {'name': 'Malta', 'flag': '🇲🇹'},
            '357': {'name': 'Cyprus', 'flag': '🇨🇾'},
            '358': {'name': 'Finland', 'flag': '🇫🇮'},
            '359': {'name': 'Bulgaria', 'flag': '🇧🇬'},
            '370': {'name': 'Lithuania', 'flag': '🇱🇹'},
            '371': {'name': 'Latvia', 'flag': '🇱🇻'},
            '372': {'name': 'Estonia', 'flag': '🇪🇪'},
            '373': {'name': 'Moldova', 'flag': '🇲🇩'},
            '374': {'name': 'Armenia', 'flag': '🇦🇲'},
            '375': {'name': 'Belarus', 'flag': '🇧🇾'},
            '376': {'name': 'Andorra', 'flag': '🇦🇩'},
            '377': {'name': 'Monaco', 'flag': '🇲🇨'},
            '378': {'name': 'San Marino', 'flag': '🇸🇲'},
            '380': {'name': 'Ukraine', 'flag': '🇺🇦'},
            '381': {'name': 'Serbia', 'flag': '🇷🇸'},
            '382': {'name': 'Montenegro', 'flag': '🇲🇪'},
            '383': {'name': 'Kosovo', 'flag': '🇽🇰'},
            '385': {'name': 'Croatia', 'flag': '🇭🇷'},
            '386': {'name': 'Slovenia', 'flag': '🇸🇮'},
            '387': {'name': 'Bosnia and Herzegovina', 'flag': '🇧🇦'},
            '389': {'name': 'North Macedonia', 'flag': '🇲🇰'},
            '420': {'name': 'Czech Republic', 'flag': '🇨🇿'},
            '421': {'name': 'Slovakia', 'flag': '🇸🇰'},
            '423': {'name': 'Liechtenstein', 'flag': '🇱🇮'},
            '962': {'name': 'Jordan', 'flag': '🇯🇴'},
            '963': {'name': 'Syria', 'flag': '🇸🇾'},
            '964': {'name': 'Iraq', 'flag': '🇮🇶'},
            '965': {'name': 'Kuwait', 'flag': '🇰🇼'},
            '966': {'name': 'Saudi Arabia', 'flag': '🇸🇦'},
            '967': {'name': 'Yemen', 'flag': '🇾🇪'},
            '968': {'name': 'Oman', 'flag': '🇴🇲'},
            '970': {'name': 'Palestine', 'flag': '🇵🇸'},
            '971': {'name': 'UAE', 'flag': '🇦🇪'},
            '972': {'name': 'Israel', 'flag': '🇮🇱'},
            '973': {'name': 'Bahrain', 'flag': '🇧🇭'},
            '974': {'name': 'Qatar', 'flag': '🇶🇦'},
            '975': {'name': 'Bhutan', 'flag': '🇧🇹'},
            '976': {'name': 'Mongolia', 'flag': '🇲🇳'},
            '977': {'name': 'Nepal', 'flag': '🇳🇵'},
            '992': {'name': 'Tajikistan', 'flag': '🇹🇯'},
            '993': {'name': 'Turkmenistan', 'flag': '🇹🇲'},
            '994': {'name': 'Azerbaijan', 'flag': '🇦🇿'},
            '995': {'name': 'Georgia', 'flag': '🇬🇪'},
            '996': {'name': 'Kyrgyzstan', 'flag': '🇰🇬'},
            '998': {'name': 'Uzbekistan', 'flag': '🇺🇿'}
        }
        
        import re
        # Clean phone number
        cleaned_number = re.sub(r'[^\d]', '', phone_number)
        
        # Find matching country code (longest match first)
        for code in sorted(country_codes.keys(), key=len, reverse=True):
            if cleaned_number.startswith(code):
                return country_codes[code]
        
        return {'name': 'Unknown', 'flag': '🌍'}

    def format_channel_message(self, otp_data: Dict) -> str:
        """Format SMS data into original Telegram channel message format"""
        try:
            # Get basic data
            otp_code = otp_data.get('otp_code', 'Unknown')
            number = otp_data.get('number', 'Unknown')
            timestamp = otp_data.get('timestamp', 'Unknown')
            message = otp_data.get('message', 'No message')
            
            # Get country info from phone number (ORIGINAL METHOD)
            country_info = self.get_country_info_from_number(number)
            country = country_info['name']
            country_flag = country_info['flag']
            
            # Extract service name from CLI column (record[3])
            # CLI column contains the actual service name like "Telegram", "WhatsApp", etc.
            service_name = otp_data.get('service', 'Unknown')
            
            # Clean up service name if needed
            if service_name and isinstance(service_name, str) and service_name != 'Unknown':
                # Capitalize first letter for consistency
                service_name = service_name.strip().capitalize()
                
                # Handle common variations
                service_lower = service_name.lower()
                if 'telegram' in service_lower:
                    service_name = 'Telegram'
                elif 'whatsapp' in service_lower:
                    service_name = 'WhatsApp'
                elif 'facebook' in service_lower:
                    service_name = 'Facebook'
                elif 'instagram' in service_lower:
                    service_name = 'Instagram'
                elif 'google' in service_lower:
                    service_name = 'Google'
                elif 'twitter' in service_lower:
                    service_name = 'Twitter'
            
            # Clean and escape text for markdown safety
            safe_timestamp = self.escape_markdown(str(timestamp))
            safe_number = self.escape_markdown(str(number))
            safe_country = self.escape_markdown(str(country))
            safe_service = self.escape_markdown(str(service_name))
            safe_message = str(message)  # Keep message unescaped for code block
            
            # Make OTP clickable (safe from escaping)
            clickable_otp = f"`{otp_code}`" if otp_code != 'Unknown' else 'Unknown'
            
            # Original format with escaped text
            formatted_message = f"""🔔{safe_country} {country_flag} {safe_service} Otp Code Received Successfully\\.

⏰Time: {safe_timestamp}
📱Number: {safe_number}
🌍Country: {safe_country} {country_flag}
💬Service: {safe_service}
🔐Otp Code: {clickable_otp}
📝Message:
```
{safe_message}
```

Powered by @tasktreasur\\_support"""
            
            return formatted_message
            
        except Exception as e:
            logger.error(f"Error formatting channel message: {e}")
            return f"Error formatting message: {e}"

    async def notify_user_otp(self, otp_data: Dict):
        """Notify users about new OTP"""
        try:
            # Channel notification - using original format
            channel_message = self.format_channel_message(otp_data)
            
            await self.send_to_channel_direct(channel_message)
            logger.info(f"📢 Channel notified: {otp_data['otp_code']}")
            
            # Individual user notifications
            if self.number_bot:
                await self.number_bot.notify_user_otp(
                    otp_data['number'], 
                    otp_data['otp_code'], 
                    otp_data['service'], 
                    otp_data['message']
                )
            
        except Exception as e:
            logger.error(f"❌ User notification error: {e}")
    
    async def run(self):
        """Main monitoring loop"""
        logger.info("🚀 SIMPLE REQUESTS OTP BOT STARTING...")
        
        while True:
            try:
                # Login if needed
                if not self.logged_in:
                    if not self.login_once():
                        logger.error("❌ Login failed, retrying in 30 seconds...")
                        await asyncio.sleep(30)
                        continue
                
                # Check for messages
                messages = self.check_for_messages()
                
                if messages:
                    new_otps = 0
                    for msg in messages:
                        otp_data = self.extract_otp_data(msg)
                        if otp_data:
                            msg_hash = self.get_message_hash(otp_data['message'])
                            if msg_hash not in self.processed_hashes:
                                # New OTP found
                                self.processed_hashes.add(msg_hash)
                                new_otps += 1
                                
                                logger.info(f"⚡ NEW OTP: {otp_data['otp_code']} → {otp_data['service']} ({otp_data['number']})")
                                
                                # Notify users
                                await self.notify_user_otp(otp_data)
                    
                    if new_otps == 0:
                        logger.info(f"📊 Checked {len(messages)} messages - no new OTPs")
                    
                    # Cleanup old hashes
                    if len(self.processed_hashes) > self.max_hashes:
                        old_hashes = list(self.processed_hashes)[:500]
                        for old_hash in old_hashes:
                            self.processed_hashes.remove(old_hash)
                        logger.info("🧹 Cleaned old message hashes")
                
                # Reset failure count on success
                self.failure_count = 0
                
                # Wait before next check
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                self.failure_count += 1
                
                # Re-login after 10 consecutive failures
                if self.failure_count >= 10:
                    logger.warning("🔄 Too many failures, forcing re-login...")
                    self.logged_in = False
                    self.failure_count = 0
                
                await asyncio.sleep(5)

if __name__ == "__main__":
    bot = SimpleRequestsOTPBot()
    asyncio.run(bot.run())
