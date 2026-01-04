from utills import db_cur


class Employee:
    def __init__(self, emp_id, first_name_he, last_name_he, start_date=None,
                 city=None, street=None, house_number=None, phones=None):
        self.id = emp_id
        self.first_name = first_name_he
        self.last_name = last_name_he
        self.start_date = start_date
        self.city = city
        self.street = street
        self.house_number = house_number
        self.phones = phones

    @property
    def full_address(self):
        """פונקציית עזר להצגת כתובת מלאה"""
        if self.city and self.street:
            return f"{self.street} {self.house_number}, {self.city}"
        return "כתובת לא הוזנה"


class Manager(Employee):
    def __init__(self, password, **kwargs):
        super().__init__(**kwargs)  # מעביר את כל פרטי ה-Employee למחלקת האם
        self.password = password

    @staticmethod
    def from_db(row):
        if not row: return None
        # יצירת אובייקט מנהל מתוך שורה ב-DB
        mgr = Manager(
            emp_id=row['id'],
            first_name_he=row['first_name_he'],
            last_name_he=row['last_name_he'],
            start_date=row.get('start_date'),
            city=row.get('city'),
            street=row.get('street'),
            house_number=row.get('house_number'),
            password=row.get('password')
        )
        mgr.load_phones()  # טעינת הטלפונים מיד עם היצירה
        return mgr


class Pilot(Employee):
    def __init__(self, big_aircraft_cert, **kwargs):
        super().__init__(**kwargs)
        self.big_aircraft_cert = bool(big_aircraft_cert)

    @staticmethod
    def from_db(row):
        if not row: return None
        pilot = Pilot(
            emp_id=row['id'],
            first_name_he=row['first_name_he'],
            last_name_he=row['last_name_he'],
            big_aircraft_cert=row.get('big_aircraft_cert'),
            city=row.get('city'),
            street=row.get('street'),
            house_number=row.get('house_number')
        )
        pilot.load_phones()
        return pilot


class FlightAttendant(Employee):
    def __init__(self, big_aircraft_cert, **kwargs):
        super().__init__(**kwargs)
        self.big_aircraft_cert = bool(big_aircraft_cert)

    @staticmethod
    def from_db(row):
        if not row: return None
        fa = FlightAttendant(
            emp_id=row['id'],
            first_name_he=row['first_name_he'],
            last_name_he=row['last_name_he'],
            big_aircraft_cert=row.get('big_aircraft_cert')
        )
        fa.load_phones()
        return fa