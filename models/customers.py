from utills import db_cur

class Customer:
    def __init__(self, email, first_name_en, last_name_en, phones=None):
        self.email = email
        self.first_name = first_name_en
        self.last_name = last_name_en
        self.phones = phones if phones else []

class RegisteredUser(Customer):
    def __init__(self, email, first_name_en, last_name_en, password, birth_date=None, passport=None, phones=None):
        super().__init__(email, first_name_en, last_name_en, phones)
        self.password = password
        self.birth_date = birth_date
        self.passport = passport

    def load_phones(self):
        with db_cur() as cursor:
            query = "SELECT phone_number FROM RegisteredPhone WHERE email = %s"
            cursor.execute(query, (self.email,))
            results = cursor.fetchall()
            self.phones = [row['phone_number'] for row in results]

    @staticmethod
    def from_db(row):
        if not row: return None
        user = RegisteredUser(
            email=row['email'],
            first_name_en=row['first_name_en'],
            last_name_en=row['last_name_en'],
            password=row['password'],
            birth_date=row['birth_date'],
            passport=row['passport_number']
        )
        user.load_phones() # טעינה אוטומטית של הטלפונים
        return user

class GuestUser(Customer):
    def load_phones(self):
        """שליפת טלפונים מטבלת CustomerPhone"""
        with db_cur() as cursor:
            query = "SELECT phone_number FROM CustomerPhone WHERE email = %s"
            cursor.execute(query, (self.email,))
            results = cursor.fetchall()
            self.phones = [row['phone_number'] for row in results]