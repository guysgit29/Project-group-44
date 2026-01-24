import mysql.connector
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ==========================================
# 1. הגדרות חיבור למסד הנתונים
# ==========================================
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'rootroot',  # הסיסמה שלך מהקוד ששלחת
    'database': 'flytau'
}

# ==========================================
# 2. הגדרת השאילתות
# ==========================================

# שאילתה 5: ניצולת צי (Fleet Utilization)
query_utilization = """
WITH Route_Stats AS (
    SELECT 
        aircraft_id,
        DATE_FORMAT(departure_time, '%Y-%m') AS work_month,
        CONCAT(origin, '-', destination) AS route_name,
        COUNT(*) AS route_count
    FROM Flight
    WHERE flight_status = 'Completed'
    GROUP BY aircraft_id, work_month, route_name
), 
Dominant_Routes AS (
    SELECT 
        aircraft_id,
        work_month,
        route_name,
        ROW_NUMBER() OVER (PARTITION BY aircraft_id, work_month ORDER BY route_count DESC, route_name ASC) AS rn
    FROM Route_Stats
)
SELECT 
    a.aircraft_id,
    DATE_FORMAT(f.departure_time, '%Y-%m') AS work_month,
    CONCAT(
        ROUND(
            (COUNT(DISTINCT CASE 
                WHEN f.flight_status = 'Completed' 
                THEN DATE(f.departure_time) 
            END) / 30.0) * 100, 2),'%') AS utilization_percentage
FROM Aircraft a
LEFT JOIN Flight f ON a.aircraft_id = f.aircraft_id
LEFT JOIN Dominant_Routes dr ON a.aircraft_id = dr.aircraft_id 
                        AND DATE_FORMAT(f.departure_time, '%Y-%m') = dr.work_month 
                        AND dr.rn = 1
WHERE f.departure_time <= NOW()
GROUP BY a.aircraft_id, DATE_FORMAT(f.departure_time, '%Y-%m'), dr.route_name;
"""

# שאילתה 2: הכנסות לפי סוג מטוס (Revenue Allocation)
query_revenue = """
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
GROUP BY a.aircraft_size, a.manufacturer, ra.class_type;
"""


# ==========================================
# 3. פונקציות ליצירת הגרפים
# ==========================================

def generate_fleet_chart(conn):
    """מייצרת את גרף הניצולת (שאילתה 5)"""
    print("--- Generating Fleet Utilization Chart ---")
    df = pd.read_sql(query_utilization, conn)

    if df.empty:
        print("No data for utilization.")
        return

    # עיבוד נתונים
    df['util_numeric'] = df['utilization_percentage'].str.rstrip('%').astype(float)
    df['aircraft_id'] = df['aircraft_id'].astype(str)

    # יצירת הגרף
    plt.figure(figsize=(12, 6))
    sns.set_style("whitegrid")
    ax = sns.barplot(x='aircraft_id', y='util_numeric', data=df, color='skyblue', edgecolor='black')

    # קו ייחוס
    plt.axhline(y=80, color='red', linestyle='--', linewidth=2, label='Industry Standard Target (80%)')

    # כותרות
    plt.title('Fleet Utilization Analysis: Actual vs. Target', fontsize=16, fontweight='bold')
    plt.ylabel('Monthly Utilization', fontsize=12)
    plt.xlabel('Aircraft ID', fontsize=12)
    plt.ylim(0, 100)
    plt.legend(loc='upper right')

    # ערכים מעל העמודות
    for p in ax.patches:
        height = p.get_height()
        if height > 0:
            ax.annotate(f'{height:.2f}%', (p.get_x() + p.get_width() / 2., height),
                        ha='center', va='center', xytext=(0, 8), textcoords='offset points',
                        fontsize=9, fontweight='bold')

    plt.tight_layout()
    plt.show()  # התוכנית תעצור כאן עד שתסגור את החלון
    print("Utilization chart closed.")


def generate_revenue_chart(conn):
    """מייצרת את גרף ההכנסות (שאילתה 2)"""
    print("\n--- Generating Revenue Allocation Chart ---")
    df = pd.read_sql(query_revenue, conn)

    if df.empty:
        print("No data for revenue.")
        return

    # עיבוד נתונים
    df['Category'] = df['manufacturer'] + ' - ' + df['aircraft_size']
    df['total_revenue'] = df['total_revenue'].astype(float)

    # Pivot לגרף Stacked
    df_pivot = df.pivot(index='Category', columns='class_type', values='total_revenue').fillna(0)
    if 'Business' in df_pivot.columns and 'Economy' in df_pivot.columns:
        df_pivot = df_pivot[['Economy', 'Business']]

    # יצירת הגרף
    plt.figure(figsize=(10, 6))
    ax = df_pivot.plot(kind='bar', stacked=True, figsize=(10, 6),
                       color=['#4c72b0', '#dd8452'], edgecolor='black', width=0.6)

    plt.title('Total Revenue Contribution by Fleet Segment\n(Business vs. Economy)', fontsize=16, fontweight='bold')
    plt.ylabel('Total Allocated Revenue (Currency)', fontsize=12)
    plt.xlabel('Fleet Category', fontsize=12)
    plt.xticks(rotation=0)
    plt.legend(title='Revenue Source')

    for c in ax.containers:
        ax.bar_label(c, fmt='%.0f', label_type='center', fontsize=9, color='white', fontweight='bold')

    plt.tight_layout()
    plt.show()
    print("Revenue chart closed.")


# ==========================================
# 4. התוכנית הראשית
# ==========================================
if __name__ == "__main__":
    conn = None
    try:
        print("Connecting to database...")
        conn = mysql.connector.connect(**db_config)

        # הרצת הגרף הראשון
        generate_fleet_chart(conn)

        # הרצת הגרף השני
        generate_revenue_chart(conn)

    except mysql.connector.Error as err:
        print(f"Error: {err}")

    finally:
        if conn and conn.is_connected():
            conn.close()
            print("Database connection closed.")