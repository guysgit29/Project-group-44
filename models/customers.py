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
    def login(email, password):
        """מאמת פרטי התחברות ללקוח"""
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM RegisteredUser WHERE email = %s AND password = %s", (email, password))
            return RegisteredUser.from_db(cursor.fetchone())

    @staticmethod
    def from_db(row):
        if not row: return None
        return RegisteredUser(row['email'], row['first_name_en'], row['last_name_en'],
                              row['password'], row['birth_date'], row['passport_number'])

    def save(self):
        """שומר משתמש חדש ל-DB"""
        reg_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        query = """INSERT INTO RegisteredUser (email, first_name_en, last_name_en, birth_date, 
                   registration_date, passport_number, password) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        with DB.get_cursor() as cursor:
            cursor.execute(query, (self.email, self.first_name, self.last_name, self.birth_date,
                                   reg_date, self.passport, self.password))