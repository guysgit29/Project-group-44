# models/reports.py
from database import DB

class ManagerReports:

    @staticmethod
    def report_1_avg_occupancy_past_flights():
        """
        דוח 1: ממוצע תפוסת טיסות שהתקיימו (arrival_time < NOW()) באחוזים
        """
        query = """
        SELECT
            ROUND(
                AVG(
                    (COALESCE(t.tickets_sold, 0) / sof.total_capacity) * 100
                )
            , 2) AS average_flight_occupancy_percentage
        FROM Flight f
        JOIN (
            SELECT flight_number, COUNT(*) AS total_capacity
            FROM Seats_on_Flights
            GROUP BY flight_number
        ) sof ON f.flight_number = sof.flight_number
        LEFT JOIN (
            SELECT flight_number, COUNT(*) AS tickets_sold
            FROM Ticket
            GROUP BY flight_number
        ) t ON f.flight_number = t.flight_number
        WHERE f.arrival_time < NOW();
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
            # מחזיר מספר (או 0 אם אין נתונים)
            if not row:
                return 0
            val = row.get("average_flight_occupancy_percentage")
            return float(val) if val is not None else 0

    @staticmethod
    def report_2_revenue_by_aircraft_and_class():
        """
        דוח 2: הכנסות לפי סוג מטוס/יצרן/מחלקה (allocation לפי מחירון)
        """
        query = """
        WITH Ticket_Valuation AS (
            SELECT
                t.booking_id,
                t.aircraft_id,
                t.class_type,
                cof.class_price AS individual_list_price,
                SUM(cof.class_price) OVER (PARTITION BY t.booking_id) AS total_booking_list_value
            FROM Ticket t
            JOIN Classes_on_Flights cof
                ON t.flight_number = cof.flight_number
                AND t.aircraft_id = cof.aircraft_id
                AND t.class_type = cof.class_type
        ),
        Revenue_Allocation AS (
            SELECT
                tv.aircraft_id,
                tv.class_type,
                (tv.individual_list_price / tv.total_booking_list_value) * b.price AS allocated_revenue
            FROM Ticket_Valuation tv
            JOIN Booking b ON tv.booking_id = b.booking_id
        )
        SELECT
            a.aircraft_size,
            a.manufacturer,
            ra.class_type,
            ROUND(SUM(ra.allocated_revenue), 2) AS total_revenue
        FROM Revenue_Allocation ra
        JOIN Aircraft a ON ra.aircraft_id = a.aircraft_id
        GROUP BY a.aircraft_size, a.manufacturer, ra.class_type
        ORDER BY a.aircraft_size, a.manufacturer, ra.class_type;
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall() or []

    @staticmethod
    def report_3_crew_hours_short_long():
        """
        דוח 3: שעות טיסה לכל עובד (טייס/דייל) לפי קצר/ארוך + סה"כ
        """
        query = """
        WITH All_Crew_Flights AS (
            SELECT
                p.id,
                p.first_name_he,
                p.last_name_he,
                'Pilot' AS job_title,
                fl.length_minutes
            FROM Pilot p
            JOIN Pilots_on_Flights pof ON p.id = pof.id
            JOIN Flight f ON pof.flight_number = f.flight_number
            JOIN FlightLength fl ON f.origin = fl.origin AND f.destination = fl.destination
            WHERE f.flight_status = 'Completed'

            UNION ALL

            SELECT
                fa.id,
                fa.first_name_he,
                fa.last_name_he,
                'Flight Attendant' AS job_title,
                fl.length_minutes
            FROM FlightAttendant fa
            JOIN FlightAttendants_on_Flights faof ON fa.id = faof.id
            JOIN Flight f ON faof.flight_number = f.flight_number
            JOIN FlightLength fl ON f.origin = fl.origin AND f.destination = fl.destination
            WHERE f.flight_status = 'Completed'
        )
        SELECT
            id,
            first_name_he,
            last_name_he,
            job_title,
            ROUND(SUM(CASE WHEN length_minutes <= '06:00:00' THEN TIME_TO_SEC(length_minutes)/3600 ELSE 0 END), 2) AS short_flight_hours,
            ROUND(SUM(CASE WHEN length_minutes >  '06:00:00' THEN TIME_TO_SEC(length_minutes)/3600 ELSE 0 END), 2) AS long_flight_hours,
            ROUND(SUM(TIME_TO_SEC(length_minutes)/3600), 2) AS total_hours
        FROM All_Crew_Flights
        GROUP BY id, first_name_he, last_name_he, job_title
        ORDER BY job_title, last_name_he, first_name_he;
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall() or []

    @staticmethod
    def report_4_monthly_cancellation_rate():
        """
        דוח 4: שיעור ביטולים חודשי (Customer/Manager) מתוך כלל ההזמנות
        """
        query = """
        SELECT
            DATE_FORMAT(booking_date, '%Y-%m') AS booking_month,
            COUNT(*) AS total_bookings,
            SUM(CASE
                WHEN booking_status = 'Canceled by Customer' OR booking_status = 'Canceled by Manager' THEN 1
                ELSE 0
            END) AS cancelled_count,
            ROUND(
                (SUM(CASE
                    WHEN booking_status = 'Canceled by Customer' OR booking_status = 'Canceled by Manager' THEN 1
                    ELSE 0
                END) / COUNT(*)) * 100
            , 2) AS cancellation_rate_percentage
        FROM Booking
        GROUP BY DATE_FORMAT(booking_date, '%Y-%m')
        ORDER BY booking_month;
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall() or []
