from database import DB

# =========================
# Base class
# =========================
class Employee:
    def __init__(self, id, first_name_he=None, last_name_he=None, start_date=None,
                 city=None, street=None, house_number=None):
        self.id = id
        self.first_name_he = first_name_he
        self.last_name_he = last_name_he
        self.start_date = start_date
        self.city = city
        self.street = street
        self.house_number = house_number

    @staticmethod
    def _fetch_employee_row(emp_id: int):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date, city, street, house_number
                FROM Employee
                WHERE id = %s
            """, (emp_id,))
            return cursor.fetchone()

    @classmethod
    def from_db(cls, emp_id: int):
        """טוען עובד בסיסי מהטבלה Employee"""
        row = cls._fetch_employee_row(emp_id)
        if not row:
            return None
        return cls(
            id=row["id"],
            first_name_he=row["first_name_he"],
            last_name_he=row["last_name_he"],
            start_date=row["start_date"],
            city=row["city"],
            street=row["street"],
            house_number=row["house_number"],
        )

    @staticmethod
    def role_of(emp_id: int):
        """
        מחזיר איזה תפקידים יש לעובד (יכול להיות יותר מאחד אם אפשר אצלכם).
        """
        roles = set()
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM Manager WHERE id=%s", (emp_id,))
            if cursor.fetchone(): roles.add("manager")

            cursor.execute("SELECT 1 FROM Pilot WHERE id=%s", (emp_id,))
            if cursor.fetchone(): roles.add("pilot")

            cursor.execute("SELECT 1 FROM FlightAttendant WHERE id=%s", (emp_id,))
            if cursor.fetchone(): roles.add("flight_attendant")

        return roles


# =========================
# Subclasses
# =========================
class Manager(Employee):
    def __init__(self, id, first_name_he=None, last_name_he=None, start_date=None,
                 city=None, street=None, house_number=None, password=None):
        super().__init__(id, first_name_he, last_name_he, start_date, city, street, house_number)
        self.password = password

    @classmethod
    def from_db(cls, emp_id: int):
        emp = Employee._fetch_employee_row(emp_id)
        if not emp:
            return None
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT password FROM Manager WHERE id=%s", (emp_id,))
            m = cursor.fetchone()
            if not m:
                return None
        return cls(
            id=emp["id"],
            first_name_he=emp["first_name_he"],
            last_name_he=emp["last_name_he"],
            start_date=emp["start_date"],
            city=emp["city"],
            street=emp["street"],
            house_number=emp["house_number"],
            password=m["password"],
        )

    @staticmethod
    def login(emp_id: int, password: str):
        """מאמת מנהל לפי Manager.password"""
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT E.id
                FROM Employee E
                JOIN Manager M ON E.id = M.id
                WHERE E.id = %s AND M.password = %s
            """, (emp_id, password))
            row = cursor.fetchone()
            if not row:
                return None
        return Manager.from_db(emp_id)


class Pilot(Employee):
    def __init__(self, id, first_name_he=None, last_name_he=None, start_date=None,
                 city=None, street=None, house_number=None, big_aircraft_cert=None):
        super().__init__(id, first_name_he, last_name_he, start_date, city, street, house_number)
        self.big_aircraft_cert = big_aircraft_cert

    @classmethod
    def from_db(cls, emp_id: int):
        emp = Employee._fetch_employee_row(emp_id)
        if not emp:
            return None
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT big_aircraft_cert FROM Pilot WHERE id=%s", (emp_id,))
            p = cursor.fetchone()
            if not p:
                return None
        return cls(
            id=emp["id"],
            first_name_he=emp["first_name_he"],
            last_name_he=emp["last_name_he"],
            start_date=emp["start_date"],
            city=emp["city"],
            street=emp["street"],
            house_number=emp["house_number"],
            big_aircraft_cert=p["big_aircraft_cert"],
        )


class FlightAttendant(Employee):
    def __init__(self, id, first_name_he=None, last_name_he=None, start_date=None,
                 city=None, street=None, house_number=None, big_aircraft_cert=None):
        super().__init__(id, first_name_he, last_name_he, start_date, city, street, house_number)
        self.big_aircraft_cert = big_aircraft_cert

    @classmethod
    def from_db(cls, emp_id: int):
        emp = Employee._fetch_employee_row(emp_id)
        if not emp:
            return None
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT big_aircraft_cert FROM FlightAttendant WHERE id=%s", (emp_id,))
            fa = cursor.fetchone()
            if not fa:
                return None
        return cls(
            id=emp["id"],
            first_name_he=emp["first_name_he"],
            last_name_he=emp["last_name_he"],
            start_date=emp["start_date"],
            city=emp["city"],
            street=emp["street"],
            house_number=emp["house_number"],
            big_aircraft_cert=fa["big_aircraft_cert"],
        )


# =========================
# Optional: "Factory" loader
# =========================
def load_employee_as_roles(emp_id: int):
    """
    מחזיר אובייקטים לפי התפקידים של העובד.
    לדוגמה עובד שהוא גם Pilot וגם FlightAttendant -> תקבל 2 אובייקטים.
    """
    roles = Employee.role_of(emp_id)
    objects = []

    if "manager" in roles:
        objects.append(Manager.from_db(emp_id))
    if "pilot" in roles:
        objects.append(Pilot.from_db(emp_id))
    if "flight_attendant" in roles:
        objects.append(FlightAttendant.from_db(emp_id))

    # מסנן None אם משהו לא נטען
    return [o for o in objects if o is not None]
