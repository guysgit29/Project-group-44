# FLYTAU By Group 44

FLYTAU is a web-based flight booking system developed as an academic project as part of two courses:
- **Database Systems Design**
- **Information Systems Engineering**

The project integrates a relational database (**MySQL**) with a **Flask** backend and **HTML/CSS** templates, providing both customer booking functionality and managerial flight operations tools.

---

## Key Assumptions

### The following assumptions were made:
- The default location of new aircrafts and staff members who have not yet operated any flights is TLV.
- Staff and aircrafts remains at the location of the last flight they participated, therefore, any future flight they are assigned to must depart from that location.
- On the Seats_on_flights table, 1=Vacant, 0=Occupied (By a customer)
- For the GuestCustomers and RegisteredCustomers tables there is a disjoint with no overlap between them.
- The departure and landing times are only on Israeli time with no time zones consideration.
- The conclusions presented on the Queries page of the Manager Dashboard are valid only for the data currently available on the website and are not updated automatically.
---
## Live Website
https://guyeylat.pythonanywhere.com/

---

## Demo Credentials

### Manager
- **Employee ID:** 123456782  
- **Password:** admin123

### Customer
- **Email:** noam.sade@example.com  
- **Password:** pass123

---

## User Capabilities

### Customer
- Search and view all available flights open for booking
- Register an account or place bookings as a guest
- View existing bookings and cancel them (registered or guest) up to **36 hours** before departure
- View full booking history (registered users only) with filtering by booking status
- Access a personal profile area and update personal details (registered users only)

### Manager
- Add and view flight routes
- Add and view company staff members
- Add and view aircraft in the company fleet
- View all flights in the system (active, full, canceled, completed) and cancel flights up to **72 hours** before departure
- Generate and view management reports about company operations
- Create new flights by allocating available aircraft and certified staff at the origin airport, with the ability to set tickets prices fot each cabin class.

---

## Software Architecture & Code Structure

The system follows the **Model-View-Controller (MVC)** architectural pattern adapted for Flask.

### 1. Controller Layer (`app.py`)
The application entry point handling HTTP routing, session management, and bridging frontend templates with backend logic.

### 2. Model Layer (`models/`)
Encapsulates business logic and database interactions:
- **`flight.py`**: Manages schedules, routes, filtering, and status updates.
- **`employees.py`**: Handles staff authentication and logic for crew assignment.
- **`booking.py`**: Processes ticket reservations, cancellations, and validations.
- **`aircraft.py`**: Manages fleet inventory and automatic seat layout generation.
- **`customers.py`**: Handles user registration, profiles, and guest data.
- **`reports.py`**: Generates SQL-based operational analytics for managers.

### 3. View Layer (`templates/`)
Jinja2 HTML templates containing the global layout (`base.html`), manager dashboards, and customer booking interfaces.

### 4. Database Utility (`database.py`)
Manages MySQL connection pooling and ensures proper resource cleanup after requests.
---

## Data (SQL Seed + Schema Diagram)

This repository includes SQL files for seeding sample data and reviewing the database structure.

- `sql/data/` – **Data scripts** (INSERTs / sample records) used for populating the DB for demo/testing.
- `sql/db/` – **Database schema scripts** (CREATE TABLE / constraints / relations) for building the database.

### Database Structure (ERD / Schema Image)
If you want to visually review the database design (entities + relations), see the ERD/scheme image in the repository:
- `sql/erd.png` 



---

## Technology Stack
- **Backend:** Python (Flask)
- **Database:** MySQL
- **Frontend:** HTML/CSS
- **Deployment:** PythonAnywhere
- **Development Environment:** PyCharm
- **Version Control:** Git & GitHub