FlyTAU By Group 44

FlyTAU is a web-based flight booking system developed as an academic project as part of two courses:
	•	Database Systems Design
	•	Information Systems Engineering

The project integrates a relational database (MySQL) with a Flask-based backend and HTML/CSS templates, providing both customer booking functionality and managerial flight operations tools.

⸻

Live Website

http://guyeylat.pythonanywhere.com/

⸻

Demo Credentials

Manager
	•	Employee ID: 123456782
	•	Password: admin123

Customer
	•	Email: noam.sade@example.com
	•	Password: pass123

⸻

User Capabilities

Customer
	•	Search and view all available flights open for booking
	•	Register an account or place bookings as a guest
	•	View existing bookings and cancel them (registered or guest) up to 36 hours before departure
	•	View full booking history (registered users only) with filtering by booking status
	•	Access a personal profile area and update personal details (registered users only)

Manager
	•	Add and view flight routes
	•	Add and view company staff members
	•	Add and view aircraft in the company fleet
	•	View all flights in the system (active, full, canceled, completed) and cancel flights up to 72 hours before departure
	•	Generate and view management reports about company operations

⸻

Project Structure
	•	app.py – Main Flask application (routes and controllers)
	•	models/ – Business logic and database queries (customers, flights, bookings, employees, reports, aircrafts)
	•	templates/ – HTML templates (Jinja2)
	•	static/ – CSS and static assets
	•	database.py – Database connection handler (MySQL)


⸻

Technology Stack
	•	Backend: Python (Flask)
	•	Database: MySQL
	•	Frontend: HTML/CSS
	•	Deployment: PythonAnywhere