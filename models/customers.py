from database import DB
from datetime import datetime


class RegisteredUser:
    def __init__(
        self,
        email: str,
        first_name_en: str,
        last_name_en: str,
        password: str,
        birth_date=None,
        passport_number=None,
        registration_date=None
    ):
        self.email = (email or "").strip().lower()
        self.first_name = first_name_en
        self.last_name = last_name_en
        self.password = password
        self.birth_date = birth_date
        self.passport = passport_number
        self.registration_date = registration_date

    # ---------- Queries ----------

    @staticmethod
    def get_by_email(email: str):
        email = (email or "").strip().lower()
        if not email:
            return None

        with DB.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM RegisteredUser WHERE LOWER(email) = %s LIMIT 1",
                (email,)
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
            registration_date=row.get("registration_date"),
        )

    @staticmethod
    def email_exists(email: str) -> bool:
        email = (email or "").strip().lower()
        if not email:
            return False

        with DB.get_cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM RegisteredUser WHERE LOWER(email) = %s LIMIT 1",
                (email,)
            )
            return cursor.fetchone() is not None

    @staticmethod
    def login(email: str, password: str):
        """
        מאפשר התחברות של לקוח רשום.
        ה-uid אצלך ב-login_page יכול להיות email, אז נתמך.
        """
        email = (email or "").strip().lower()
        password = (password or "").strip()
        if not email or not password:
            return None

        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM RegisteredUser
                WHERE LOWER(email) = %s AND password = %s
                LIMIT 1
                """,
                (email, password)
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
            registration_date=row.get("registration_date"),
        )

    # ---------- Registration flow ----------

    @staticmethod
    def register(data):
        """
        מרכז את לוגיקת ההרשמה.
        מחזיר (user, None) או (None, error_message)
        """
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "").strip()
        confirm_password = (data.get("confirm_password") or "").strip()

        first_name = (data.get("first_name") or "").strip()
        last_name = (data.get("last_name") or "").strip()
        birth_date = data.get("birth_date")  # יכול להגיע כמחרוזת YYYY-MM-DD
        passport_number = data.get("passport_number")

        # בדיקות בסיסיות
        if not email or "@" not in email:
            return None, "אימייל לא תקין"
        if not password:
            return None, "חובה להזין סיסמה"
        if password != confirm_password:
            return None, "הסיסמאות שהוזנו אינן תואמות, אנא נסה שוב"
        if not first_name or not last_name:
            return None, "חובה להזין שם פרטי ושם משפחה"

        # בדיקה אם קיים
        if RegisteredUser.email_exists(email):
            return None, "האימייל שהוזן משוייך לחשבון קיים, אנא התחבר או צור חשבון עם מייל שונה"

        # יצירה ושמירה
        try:
            new_user = RegisteredUser(
                email=email,
                first_name_en=first_name,
                last_name_en=last_name,
                password=password,
                birth_date=birth_date,
                passport_number=passport_number,
            )
            new_user.save()
            return new_user, None
        except Exception as e:
            return None, f"Database error: {str(e)}"

    def save(self):
        """
        יוצר רשומה חדשה ב-RegisteredUser.
        """
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
                    self.first_name,
                    self.last_name,
                    self.birth_date,
                    reg_date,
                    self.passport,
                    self.password,
                ),
            )


class GuestUser:
    """
    אופציונלי. רק אם אתה משתמש ב-GuestUser כמודל.
    אם יש לך כבר מודל אחר – אפשר למחוק.
    """
    def __init__(self, email: str, first_name_en: str, last_name_en: str):
        self.email = (email or "").strip().lower()
        self.first_name = first_name_en
        self.last_name = last_name_en

    @staticmethod
    def get_by_email(email: str):
        email = (email or "").strip().lower()
        if not email:
            return None
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM GuestUser WHERE LOWER(email)=%s LIMIT 1", (email,))
            row = cursor.fetchone()
        if not row:
            return None
        return GuestUser(row.get("email"), row.get("first_name_en"), row.get("last_name_en"))