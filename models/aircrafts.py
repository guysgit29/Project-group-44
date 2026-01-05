from database import DB

class Aircraft:
    def __init__(self, aircraft_id, manufacturer, size):
        self.id = aircraft_id
        self.manufacturer = manufacturer
        self.size = size # 'Big' / 'Small'

    @staticmethod
    def get_by_id(aircraft_id):
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Aircraft WHERE aircraft_id = %s", (aircraft_id,))
            row = cursor.fetchone()
            if row:
                return Aircraft(row['aircraft_id'], row['manufacturer'], row['size'])
            return None