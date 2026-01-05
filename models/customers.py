from database import DB
from datetime import datetime

class RegisteredUser:
    def __init__(self, email, first_name_en, last_name_en, password, birth_date=None, passport_number=None):
        self.email = email
        self.first_name = first_name_en
        self.last_name = last_name_en
        self.password = password
        self.birth_date = birth_date
        self.passport = passport_number

    @staticmethod
    def register(data):
        """פונקציה שמרכזת את כל לוגיקת ההרשמה"""
        email = data.get('email', '').strip().lower()
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        # 1. בדיקת התאמת סיסמאות
        if password != confirm_password:
            return None, "הסיסמאות שהוזנו אינן תואמות, אנא נסה שוב"

        # 2. בדיקה אם המשתמש כבר קיים
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM RegisteredUser WHERE email = %s", (email,))
            if cursor.fetchone():
                return None, "האימייל שהוזן משוייך לחשבון קיים, אנא התחבר או צור חשבון עם מייל שונה"

        # 3. יצירת האובייקט ושמירה ל-DB
        try:
            new_user = RegisteredUser(
                email, data.get('first_name'), data.get('last_name'),
                password, data.get('birth_date'), data.get('passport_number')
            )
            new_user.save()
            return new_user, None
        except Exception as e:
            return None, f"Database error: {str(e)}"

    def save(self):
        reg_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        query = """INSERT INTO RegisteredUser (email, first_name_en, last_name_en, birth_date, 
                   registration_date, passport_number, password) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        with DB.get_cursor() as cursor:
            cursor.execute(query, (self.email, self.first_name, self.last_name, self.birth_date,
                                   reg_date, self.passport, self.password))

    @staticmethod
    def login(email, password):
        """מחפש משתמש בטבלת RegisteredUser לפי אימייל וסיסמה"""
        query = """
                SELECT email, first_name_en, last_name_en, password, birth_date, passport_number
                FROM RegisteredUser 
                WHERE email = %s AND password = %s
            """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (email.strip().lower(), password))
            result = cursor.fetchone()

            if result:
                # יצירת אובייקט מהנתונים שחזרו (שימוש בשמות המפתחות כפי שמופיעים ב-SELECT)
                return RegisteredUser(
                    email=result['email'],
                    first_name_en=result['first_name_en'],
                    last_name_en=result['last_name_en'],
                    password=result['password'],
                    birth_date=result['birth_date'],
                    passport_number=result['passport_number']
                )
        return None