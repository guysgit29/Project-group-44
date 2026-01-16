from database import DB
from datetime import datetime
import re
class RegisteredUser:
    def __init__(self, email, first_name_en, last_name_en, password, birth_date=None, passport_number=None, registration_date=None):
        self.email = (email or "").strip().lower()
        self.first_name = first_name_en
        self.last_name = last_name_en
        self.password = password
        self.birth_date = birth_date
        self.passport = passport_number
        self.registration_date = registration_date

    @staticmethod
    def _dbg(msg: str): print(f"[DBG][RegisteredUser] {msg}")  # Print debug messages for user operations

    @staticmethod
    def get_by_email(email: str):  # Fetch a registered user by email (case-insensitive)
        email = (email or "").strip().lower()
        if not email:
            return None
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM RegisteredUser WHERE LOWER(email) = %s", (email,))
            row = cursor.fetchone()
            if not row:
                return None
            return RegisteredUser(
                email=row.get("email"),
                first_name_en=row.get("first_name_en"),
                last_name_en=row.get("last_name_en"),
                password=row.get("password"),
                birth_date=row.get("birth_date"),
                passport_number=row.get("passport_number"),
                registration_date=row.get("registration_date"),
            )

    @staticmethod
    def email_exists(email: str) -> bool:  # Check if a registered user already exists for this email
        email = (email or "").strip().lower()
        if not email:
            return False
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM RegisteredUser WHERE LOWER(email) = %s LIMIT 1", (email,))
            return cursor.fetchone() is not None

    @staticmethod
    def list_phones(email: str) -> list[str]:  # Return all saved phone numbers for a registered user
        email = (email or "").strip().lower()
        if not email:
            return []
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT phone_number
                FROM RegisteredPhone
                WHERE LOWER(email) = %s
                ORDER BY phone_number
                """,
                (email,),
            )
            rows = cursor.fetchall() or []
            return [r.get("phone_number") for r in rows if r.get("phone_number")]

    @staticmethod
    def add_phone(email: str, phone_number: str):  # Add a phone number for a user (ignores duplicates)
        email = (email or "").strip().lower()
        phone_number = (phone_number or "").strip()
        if not email:
            return False, "אימייל חסר"
        if not phone_number:
            return False, "מספר טלפון ריק"
        with DB.get_cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO RegisteredPhone (email, phone_number) VALUES (%s, %s)",
                (email, phone_number),
            )
        return True, None

    @staticmethod
    def delete_phone(email: str, phone_number: str):  # Delete a specific phone number for a user
        email = (email or "").strip().lower()
        phone_number = (phone_number or "").strip()
        if not email or not phone_number:
            return False, "נתונים חסרים"
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM RegisteredPhone
                WHERE LOWER(email)=%s AND phone_number=%s
                """,
                (email, phone_number),
            )
        return True, None

    @staticmethod
    def _parse_phones_multiline(raw: str) -> list[str]:  # Parse multiline/comma-separated phones into a deduped list (preserves order)
        raw = (raw or "").strip()
        if not raw:
            return []
        raw = raw.replace(",", "\n")
        parts = []
        for line in raw.splitlines():
            p = line.strip()
            if p:
                p = re.sub(r"\s+", "", p)
                parts.append(p)
        seen, out = set(), []
        for p in parts:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    @staticmethod
    def parse_phones(raw: str) -> list[str]: return RegisteredUser._parse_phones_multiline(raw)  # Public alias for phone parsing

    @staticmethod
    def replace_phones_from_text(email: str, phones_text: str):  # Replace all phone numbers for a user from textarea input
        email = (email or "").strip().lower()
        if not email:
            return False, "אימייל חסר"
        phones = RegisteredUser._parse_phones_multiline(phones_text)
        with DB.get_cursor() as cursor:
            cursor.execute("DELETE FROM RegisteredPhone WHERE LOWER(email)=%s", (email,))
            for p in phones:
                cursor.execute(
                    "INSERT IGNORE INTO RegisteredPhone (email, phone_number) VALUES (%s, %s)",
                    (email, p),
                )
        return True, None

    @staticmethod
    def get_profile_with_phones(email: str):  # Load user profile and all phones in one call
        email = (email or "").strip().lower()
        if not email:
            return None, []
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT email, first_name_en, last_name_en, password,
                       birth_date, passport_number, registration_date
                FROM RegisteredUser
                WHERE LOWER(email) = %s
                LIMIT 1
                """,
                (email,),
            )
            ru = cursor.fetchone()
            if not ru:
                return None, []
            cursor.execute(
                """
                SELECT phone_number
                FROM RegisteredPhone
                WHERE LOWER(email) = %s
                ORDER BY phone_number
                """,
                (email,),
            )
            rows = cursor.fetchall() or []
            phones = [r.get("phone_number") for r in rows if r.get("phone_number")]
        user = RegisteredUser(
            email=ru.get("email"),
            first_name_en=ru.get("first_name_en"),
            last_name_en=ru.get("last_name_en"),
            password=ru.get("password"),
            birth_date=ru.get("birth_date"),
            passport_number=ru.get("passport_number"),
            registration_date=ru.get("registration_date"),
        )
        return user, phones
    def save(self):  # Insert a new RegisteredUser row into the database
        reg_date = datetime.now().strftime("%Y-%m-%d")
        query = """
            INSERT INTO RegisteredUser
              (email, first_name_en, last_name_en, birth_date, registration_date, passport_number, password)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s)
        """
        with DB.get_cursor() as cursor:
            cursor.execute(
                query,
                (self.email, self.first_name, self.last_name, self.birth_date, reg_date, self.passport, self.password),
            )

    @staticmethod
    def register(data: dict):  # Create a new registered user and store all provided phone numbers
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        confirm_password = data.get("confirm_password") or ""
        phone_numbers_text = (data.get("phone_numbers") or "").strip()
        phones = RegisteredUser._parse_phones_multiline(phone_numbers_text)
        single_phone = (data.get("phone_number") or "").strip()
        if single_phone and single_phone not in phones:
            phones.append(single_phone)
        if not email:
            return None, "אימייל חסר"
        if password != confirm_password:
            return None, "הסיסמאות שהוזנו אינן תואמות, אנא נסה שוב"
        if RegisteredUser.email_exists(email):
            return None, "האימייל שהוזן משוייך לחשבון קיים, אנא התחבר או צור חשבון עם מייל שונה"
        if not phones:
            return None, "אנא הזן לפחות מספר טלפון אחד"
        try:
            new_user = RegisteredUser(
                email=email,
                first_name_en=data.get("first_name"),
                last_name_en=data.get("last_name"),
                password=password,
                birth_date=data.get("birth_date"),
                passport_number=data.get("passport_number"),
            )
            new_user.save()
            for ph in phones:
                RegisteredUser.add_phone(email, ph)
            return new_user, None
        except Exception as e:
            return None, f"Database error: {str(e)}"

    @staticmethod
    def update_profile_and_phones(email: str, first_name_en: str, last_name_en: str, birth_date, passport_number: str, phones_text: str, password: str = None):  # Update profile fields and replace phones in one transaction
        email = (email or "").strip().lower()
        if not email:
            return False, "אימייל חסר"
        first_name_en = (first_name_en or "").strip()
        last_name_en = (last_name_en or "").strip()
        passport_number = (passport_number or "").strip()
        if not first_name_en or not last_name_en:
            return False, "שם פרטי ושם משפחה הם שדות חובה"
        bd = birth_date.strip() or None if isinstance(birth_date, str) else birth_date
        phones = RegisteredUser._parse_phones_multiline(phones_text)
        if not phones:
            return False, "אנא הזן לפחות מספר טלפון אחד"
        with DB.get_cursor() as cursor:
            if password is None or str(password).strip() == "":
                cursor.execute(
                    """
                    UPDATE RegisteredUser
                    SET first_name_en=%s,
                        last_name_en=%s,
                        birth_date=%s,
                        passport_number=%s
                    WHERE LOWER(email)=%s
                    """,
                    (first_name_en, last_name_en, bd, passport_number, email),
                )
            else:
                cursor.execute(
                    """
                    UPDATE RegisteredUser
                    SET first_name_en=%s,
                        last_name_en=%s,
                        birth_date=%s,
                        passport_number=%s,
                        password=%s
                    WHERE LOWER(email)=%s
                    """,
                    (first_name_en, last_name_en, bd, passport_number, password, email),
                )
            cursor.execute("DELETE FROM RegisteredPhone WHERE LOWER(email)=%s", (email,))
            for p in phones:
                cursor.execute(
                    "INSERT IGNORE INTO RegisteredPhone (email, phone_number) VALUES (%s, %s)",
                    (email, p),
                )
        return True, None

    @staticmethod
    def login(email, password):  # Authenticate a registered user by email and password
        email = (email or "").strip().lower()
        password = password or ""
        query = """
            SELECT email, first_name_en, last_name_en, password, birth_date, passport_number, registration_date
            FROM RegisteredUser
            WHERE LOWER(email) = %s AND password = %s
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (email, password))
            result = cursor.fetchone()
            if result:
                return RegisteredUser(
                    email=result.get("email"),
                    first_name_en=result.get("first_name_en"),
                    last_name_en=result.get("last_name_en"),
                    password=result.get("password"),
                    birth_date=result.get("birth_date"),
                    passport_number=result.get("passport_number"),
                    registration_date=result.get("registration_date"),
                )
        return None


    @staticmethod
    def get_full_name_by_email(email: str) -> str:  # Resolve a customer's full name by email (RegisteredUser, else GuestUser)
        email = (email or "").strip().lower()
        if not email:
            return ""

        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT first_name_en, last_name_en
                FROM RegisteredUser
                WHERE LOWER(email) = %s
                LIMIT 1
                """,
                (email,),
            )
            row = cursor.fetchone()

            if not row:
                cursor.execute(
                    """
                    SELECT first_name_en, last_name_en
                    FROM GuestUser
                    WHERE LOWER(email) = %s
                    LIMIT 1
                    """,
                    (email,),
                )
                row = cursor.fetchone()

        if not row:
            return ""

        first = (row.get("first_name_en") or "").strip()
        last = (row.get("last_name_en") or "").strip()
        return f"{first} {last}".strip()

    @staticmethod
    def split_phones_text(raw: str) -> list[str]:  # Split multiline/comma-separated phone text into unique values (preserves appearance order)
        raw = (raw or "").strip()
        if not raw:
            return []

        raw = raw.replace(",", "\n")
        out, seen = [], set()
        for p in (x.strip() for x in raw.splitlines()):
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        return out