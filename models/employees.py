from database import DB

class Manager:
    def __init__(self, id, first_name=None, password=None):
        self.id = id
        self.first_name = first_name
        self.password = password

    @staticmethod
    def login(id, password):
        """מאמת מנהל"""
        with DB.get_cursor() as cursor:
            cursor.execute("""SELECT E.id, E.first_name_he, M.password FROM Employee E 
                              JOIN Manager M ON E.id = M.id WHERE E.id = %s AND M.password = %s""", (id, password))
            row = cursor.fetchone()
            if row: return Manager(row['id'], row['first_name_he'], row['password'])
            return None