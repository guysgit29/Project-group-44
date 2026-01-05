from database import DB

class Booking:
    def __init__(self, booking_id, flight_number, price, status, reg_email=None, guest_email=None):
        self.booking_id = booking_id
        self.flight_number = flight_number
        self.price = price
        self.status = status
        self.reg_email = reg_email
        self.guest_email = guest_email

    @staticmethod
    def get_by_id_and_email(booking_id, email):
        """חיפוש הזמנה לפי מזהה ואימייל"""
        query = "SELECT * FROM Booking WHERE booking_id = %s AND (registered_email = %s OR guest_email = %s)"
        with DB.get_cursor() as cursor:
            cursor.execute(query, (booking_id, email, email))
            return Booking.from_db(cursor.fetchone())

    @staticmethod
    def from_db(row):
        if not row: return None
        return Booking(row['booking_id'], row['flight_number'], row['price'],
                       row['booking_status'], row.get('registered_email'), row.get('guest_email'))

    def get_details(self):
        """שליפת פרטי הזמנה מלאים כולל טיסה ומושבים"""
        with DB.get_cursor() as cursor:
            cursor.execute("""SELECT b.*, f.origin, f.destination, f.departure_time, f.arrival_time, f.flight_status
                              FROM Booking b JOIN Flight f ON b.flight_number = f.flight_number
                              WHERE b.booking_id = %s""", (self.booking_id,))
            order_info = cursor.fetchone()
            cursor.execute("SELECT * FROM Ticket WHERE booking_id = %s", (self.booking_id,))
            seats = cursor.fetchall()
            return order_info, seats

    def cancel(self):
        """מחיקת מושבים ועדכון מחיר ל-5%"""
        with DB.get_cursor() as cursor:
            cursor.execute("DELETE FROM Ticket WHERE booking_id = %s", (self.booking_id,))
            cursor.execute("UPDATE Booking SET booking_status = 'Canceled by Customer', price = price / 20 WHERE booking_id = %s",
                           (self.booking_id,))