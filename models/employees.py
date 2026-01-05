from database import DB
class Employee:
    def __init__(self, id, first_name_he, last_name_he, start_date,
                 city, street, house_number):
        self.id = id
        self.first_name_he = first_name_he
        self.last_name_he = last_name_he
        self.start_date = start_date
        self.city = city
        self.street = street
        self.house_number = house_number

class Manager(Employee):
    def __init__(self, id, first_name_he, last_name_he, start_date,
                 city, street, house_number, password):
        super().__init__(id, first_name_he, last_name_he, start_date,
                         city, street, house_number)
        self.password = password

    @staticmethod
    def login(emp_id: int, password: str):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date,
                       city, street, house_number, password
                FROM manager
                WHERE id = %s AND password = %s
            """, (emp_id, password))

            row = cursor.fetchone()
            if not row:
                return None

            return Manager(
                row["id"],
                row["first_name_he"],
                row["last_name_he"],
                row["start_date"],
                row["city"],
                row["street"],
                row["house_number"],
                row["password"]
            )
