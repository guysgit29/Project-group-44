from database import DB


class Booking:
    def __init__(self, booking_id, flight_number, price, status='Active'):
        self.booking_id = booking_id
        self.flight_number = flight_number
        self.price = price
        self.status = status

    @staticmethod
    def get_by_id(booking_id):
        """
        FIX FOR AttributeError: Fetches a booking object by its ID.

        """
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Booking WHERE booking_id = %s", (booking_id,))
            row = cursor.fetchone()
            return Booking.from_db(row) if row else None

    @staticmethod
    def get_by_id_and_email(booking_id, email):
        """Used for public booking search"""
        query = "SELECT * FROM Booking WHERE booking_id = %s AND (registered_email = %s OR guest_email = %s)"
        with DB.get_cursor() as cursor:
            cursor.execute(query, (booking_id, email, email))
            row = cursor.fetchone()
            return Booking.from_db(row) if row else None

    def get_details(self):
        """Fixes AttributeError for manage_booking page"""
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT B.*, F.origin, F.destination, F.departure_time, F.arrival_time, F.flight_status,
                COALESCE(B.registered_email, B.guest_email) as email
                FROM Booking B JOIN Flight F ON B.flight_number = F.flight_number
                WHERE B.booking_id = %s""", (self.booking_id,))
            order = cursor.fetchone()

            cursor.execute("SELECT * FROM Ticket WHERE booking_id = %s", (self.booking_id,))
            seats = cursor.fetchall()
            return order, seats

    def cancel(self):
        """The actual business logic that updates the SQL status"""
        with DB.get_cursor() as cursor:
            # שלב 1: שחרור המושבים
            cursor.execute("DELETE FROM Ticket WHERE booking_id = %s", (self.booking_id,))
            # שלב 2: עדכון סטטוס ומחיר (דמי ביטול 5%)
            cursor.execute("""
                UPDATE Booking 
                SET booking_status = 'Canceled by Customer', price = price * 0.05 
                WHERE booking_id = %s
            """, (self.booking_id,))

    @staticmethod
    def from_db(row):
        """Helper to convert DB row to Python object"""
        if not row: return None
        return Booking(row['booking_id'], row['flight_number'], row['price'], row['booking_status'])