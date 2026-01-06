from __future__ import annotations

from datetime import datetime
from database import DB

class RegisteredUser:
    def __init__(
        self,
        email,
        first_name_en,
        last_name_en,
        password,
        birth_date=None,
        passport_number=None,
    ):
        self.email = email
        self.first_name_en = first_name_en
        self.last_name_en = last_name_en
        self.password = password
        self.birth_date = birth_date
        self.passport_number = passport_number

    # ----------------------------
    # Debug helper
    # ----------------------------
    @staticmethod
    def _dbg(msg: str):
        print(f"[DBG][RegisteredUser] {msg}")

    # ----------------------------
    # Lookup helpers
    # ----------------------------
    @staticmethod
    def get_by_email(email: str):
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
            )

    @staticmethod
    def email_exists(email: str) -> bool:
        email = (email or "").strip().lower()
        RegisteredUser._dbg(f"email_exists(email={email})")
        if not email:
            RegisteredUser._dbg("email_exists: empty -> False")
            return False

        with DB.get_cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM RegisteredUser WHERE LOWER(email) = %s LIMIT 1",
                (email,),
            )
            exists = cursor.fetchone() is not None
            RegisteredUser._dbg(f"email_exists: {exists}")
            return exists

    # ----------------------------
    # Auth
    # ----------------------------
    @staticmethod
    def login(email: str, password: str):
        email = (email or "").strip().lower()
        password = (password or "").strip()
        if not email or not password:
            return None

        with DB.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM RegisteredUser WHERE LOWER(email) = %s AND password = %s",
                (email, password),
            )
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
            )

    # ----------------------------
    # Registration flow
    # ----------------------------
    @staticmethod
    def register(data):
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "").strip()
        confirm_password = (data.get("confirm_password") or "").strip()

        if not email:
            return None, "יש להזין אימייל"
        if not password:
            return None, "יש להזין סיסמה"

        if password != confirm_password:
            return None, "הסיסמאות שהוזנו אינן תואמות, אנא נסה שוב"

        if RegisteredUser.email_exists(email):
            return None, "האימייל שהוזן משוייך לחשבון קיים, אנא התחבר או צור חשבון עם מייל שונה"

        try:
            new_user = RegisteredUser(
                email=email,
                first_name_en=(data.get("first_name") or "").strip(),
                last_name_en=(data.get("last_name") or "").strip(),
                password=password,
                birth_date=data.get("birth_date"),
                passport_number=data.get("passport_number"),
            )
            new_user.save()
            return new_user, None
        except Exception as e:
            return None, f"Database error: {str(e)}"

    def save(self):
        reg_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = """
            INSERT INTO RegisteredUser
              (email, first_name_en, last_name_en, birth_date, registration_date, passport_number, password)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s)
        """
        with DB.get_cursor() as cursor:
            cursor.execute(
                query,
                (
                    self.email,
                    self.first_name_en,
                    self.last_name_en,
                    self.birth_date,
                    reg_date,
                    self.passport_number,
                    self.password,
                ),
            )