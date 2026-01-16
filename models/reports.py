# models/reports.py
from database import DB
class ManagerReports:
    @staticmethod
    def report_1_avg_occupancy_past_flights():
        """
        Query 1:
        ממוצע תפוסת טיסות שהתקיימו (arrival_time < NOW()) באחוזים
        ""
        query = """
        SELECT
    ROUND(
        AVG(
            (COALESCE(t.tickets_sold, 0) / (sof.total_capacity * 1.0)) * 100
        ),
        2
    ) AS average_flight_occupancy_percentage
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
            if not row:
                return 0
            val = row.get("average_flight_occupancy_percentage")
            return float(val) if val is not None else 0

    @staticmethod
    def report_2_revenue_by_aircraft_and_class():
        """
        Query 2:
        הכנסות לפי גודל מטוס/יצרן/מחלקה עם הקצאת הכנסה לפי מחירון
        """
        query = """
        WITH Ticket_Valuation AS (
            SELECT 
                t.booking_id,
                t.aircraft_id,
                t.class_type,
                cof.class_price AS individual_list_price,
                SUM(cof.class_price) OVER (PARTITION BY t.booking_id) AS total_booking_list_value
            FROM 
                Ticket t
            JOIN 
                Classes_on_Flights cof 
                ON t.flight_number = cof.flight_number 
                AND t.aircraft_id = cof.aircraft_id 
                AND t.class_type = cof.class_type
        ),
        Revenue_Allocation AS (
            SELECT 
                tv.aircraft_id,
                tv.class_type,
                (tv.individual_list_price / tv.total_booking_list_value) * b.price AS allocated_revenue
            FROM 
                Ticket_Valuation tv
            JOIN 
                Booking b ON tv.booking_id = b.booking_id
        )
        SELECT 
            a.aircraft_size,      
            a.manufacturer,        
            ra.class_type,         
            ROUND(SUM(ra.allocated_revenue), 2) AS total_revenue
        FROM 
            Revenue_Allocation ra
        JOIN 
            Aircraft a ON ra.aircraft_id = a.aircraft_id
        GROUP BY 
            a.aircraft_size, 
            a.manufacturer, 
            ra.class_type;
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall() or []

    @staticmethod
    def report_3_crew_hours_short_long():
        """
        Query 3:
        שעות טיסה לכל עובד (טייס/דייל) לפי קצר/ארוך (Completed בלבד)
        """
        query = """
        WITH All_Crew_Flights AS (
            SELECT 
                p.id,
                p.first_name_he,
                p.last_name_he,
                fl.length_minutes
            FROM 
                Pilot p
            JOIN Pilots_on_Flights pof ON p.id = pof.id
            JOIN Flight f ON pof.flight_number = f.flight_number
            JOIN FlightLength fl ON f.origin = fl.origin AND f.destination = fl.destination
            WHERE f.flight_status = 'Completed'

            UNION ALL

            SELECT 
                fa.id,
                fa.first_name_he,
                fa.last_name_he,
                fl.length_minutes
            FROM 
                FlightAttendant fa
            JOIN FlightAttendants_on_Flights faof ON fa.id = faof.id
            JOIN Flight f ON faof.flight_number = f.flight_number
            JOIN FlightLength fl ON f.origin = fl.origin AND f.destination = fl.destination
            WHERE f.flight_status = 'Completed'
        )
        SELECT 
            id,
            first_name_he,
            last_name_he,
            ROUND(SUM(CASE 
                WHEN length_minutes <= '06:00:00' THEN TIME_TO_SEC(length_minutes) / 3600 
                ELSE 0 
            END), 2) AS short_flight_hours,
            ROUND(SUM(CASE 
                WHEN length_minutes > '06:00:00' THEN TIME_TO_SEC(length_minutes) / 3600 
                ELSE 0 
            END), 2) AS long_flight_hours
        FROM 
            All_Crew_Flights
        GROUP BY 
            id, first_name_he, last_name_he;
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall() or []

    @staticmethod
    def report_4_monthly_cancellation_rate():
        """
        Query 4:
        שיעור ביטולים חודשי מתוך כלל ההזמנות
        (Canceled by Customer / Canceled by Airline) + אחוז כמחרוזת עם '%'
        """
        query = """
        SELECT 
            DATE_FORMAT(booking_date, '%Y-%m') AS booking_month,
            CONCAT(
                ROUND(
                    (SUM(CASE 
                        WHEN booking_status IN ('Canceled by Customer', 'Canceled by Airline') THEN 1 
                        ELSE 0 
                     END) / COUNT(*)) * 100, 0
                ),
                '%'
            ) AS cancellation_rate_percentage
        FROM 
            Booking
        GROUP BY 
            DATE_FORMAT(booking_date, '%Y-%m')
        ORDER BY 
            booking_month;
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall() or []

    @staticmethod
    def report_5_fleet_monthly_utilization_and_dominant_route():
        """
        Query 5:
        דוח צי חודשי לכל מטוס:
        - performed_flights (Completed)
        - cancelled_flights (Canceled)
        - utilization_percentage לפי ימים שונים שבוצעו בהם טיסות / 30
        - dominant_route: המסלול השכיח באותו חודש (Completed) או 'No Flights'
        """
        query = """
        WITH Route_Stats AS (
            SELECT 
                aircraft_id,
                DATE_FORMAT(departure_time, '%Y-%m') AS work_month,
                CONCAT(origin, '-', destination) AS route_name,
                COUNT(*) AS route_count
            FROM 
                Flight
            WHERE 
                flight_status = 'Completed'
            GROUP BY 
                aircraft_id, work_month, route_name
        ), 
        Dominant_Routes AS (
            SELECT 
                aircraft_id,
                work_month,
                route_name,
                ROW_NUMBER() OVER (
                    PARTITION BY aircraft_id, work_month
                    ORDER BY route_count DESC, route_name ASC
                ) AS rn
            FROM 
                Route_Stats
        )
        SELECT 
            a.aircraft_id,
            DATE_FORMAT(f.departure_time, '%Y-%m') AS work_month,
            SUM(CASE 
                WHEN f.flight_status = 'Completed' THEN 1 
                ELSE 0 
            END) AS performed_flights,
            SUM(CASE 
                WHEN f.flight_status = 'Canceled' THEN 1 
                ELSE 0 
            END) AS cancelled_flights,
            CONCAT(
                ROUND(
                    (COUNT(DISTINCT CASE 
                        WHEN f.flight_status = 'Completed' 
                        THEN DATE(f.departure_time) 
                    END) / 30.0) * 100, 0
                ),
                '%'
            ) AS utilization_percentage,
            IFNULL(dr.route_name, 'No Flights') AS dominant_route
        FROM 
            Aircraft a
        LEFT JOIN 
            Flight f ON a.aircraft_id = f.aircraft_id
        LEFT JOIN 
            Dominant_Routes dr 
                ON a.aircraft_id = dr.aircraft_id 
                AND DATE_FORMAT(f.departure_time, '%Y-%m') = dr.work_month 
                AND dr.rn = 1
        GROUP BY 
            a.aircraft_id, 
            DATE_FORMAT(f.departure_time, '%Y-%m'),
            dr.route_name;
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall() or []
