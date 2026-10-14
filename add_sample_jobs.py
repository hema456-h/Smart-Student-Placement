"""Bulk-add sample companies and jobs to placement_management.db.

Usage:  python add_sample_jobs.py
Safe to run more than once: companies and (company, role) pairs that already
exist are skipped, and existing data is never changed.
"""
import os
import sqlite3
from datetime import date, datetime, timedelta

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "placement_management.db")

COMPANIES = {
    "ABC Technologies": ("Product engineering company building SaaS tools for retail.", "https://example.com/abc", "Chennai"),
    "XYZ Solutions": ("IT services and web solutions for banking clients.", "https://example.com/xyz", "Bengaluru"),
    "Zenith Systems": ("Embedded and electronics design firm.", "https://example.com/zenith", "Hyderabad"),
    "Infiniti Software": ("Enterprise software and cloud migration partner.", "https://example.com/infiniti", "Chennai"),
    "BrightPath Digital": ("Web and mobile agency for startups.", "https://example.com/brightpath", "Coimbatore"),
    "DataCrest Analytics": ("Analytics and business intelligence consulting.", "https://example.com/datacrest", "Pune"),
    "NovaCloud Systems": ("Cloud infrastructure and DevOps services.", "https://example.com/novacloud", "Bengaluru"),
    "SecureNet Labs": ("Cybersecurity products and managed security services.", "https://example.com/securenet", "Hyderabad"),
    "PixelForge Studios": ("UI/UX design and front-end engineering studio.", "https://example.com/pixelforge", "Kochi"),
    "Voltix Electronics": ("Power electronics and automation solutions.", "https://example.com/voltix", "Chennai"),
    "Orbit Telecom": ("Telecom networks and 5G equipment.", "https://example.com/orbit", "Pune"),
    "GreenGrid Energy": ("Renewable energy and smart grid engineering.", "https://example.com/greengrid", "Madurai"),
    "Titan Mechanical Works": ("Automotive components and precision manufacturing.", "https://example.com/titan", "Hosur"),
    "BuildRight Constructions": ("Infrastructure and civil construction projects.", "https://example.com/buildright", "Chennai"),
    "FinEdge Payments": ("Fintech platform for digital payments.", "https://example.com/finedge", "Mumbai"),
    "CareLink Health Tech": ("Healthcare software and patient records.", "https://example.com/carelink", "Bengaluru"),
    "EduSpark Learning": ("Online learning platform for colleges.", "https://example.com/eduspark", "Chennai"),
    "SwiftCart Commerce": ("E-commerce marketplace and logistics tech.", "https://example.com/swiftcart", "Gurugram"),
    "QuantumLeap AI": ("Applied machine learning and computer vision.", "https://example.com/quantumleap", "Bengaluru"),
    "Apex Global Services": ("Business process and technical support outsourcing.", "https://example.com/apex", "Chennai"),
}

# company, role, LPA, type, min CGPA, departments, skills, max backlogs, grad year (0=any), min %, deadline days, description
JOBS = [
    ("ABC Technologies", "Software Developer", 5, "Full-time", 7.0, "CSE, IT", "Java, Python, SQL", 0, 2026, 60, 30, "Build and test backend services for our retail platform."),
    ("ABC Technologies", "QA Engineer", 4, "Full-time", 6.5, "CSE, IT, ECE", "SQL, Git", 1, 0, 0, 22, "Write test plans and automate regression tests."),
    ("XYZ Solutions", "Web Developer", 4.5, "Full-time", 6.5, "All", "HTML, CSS, JavaScript", 1, 0, 0, 20, "Build responsive front-end interfaces for banking tools."),
    ("XYZ Solutions", "Data Analyst Intern", 3, "Internship", 8.5, "CSE, IT, AI&DS", "Python, SQL", 0, 0, 0, 15, "Six-month internship working on dashboards and reports."),
    ("Zenith Systems", "Embedded Engineer", 6, "Full-time", 7.5, "ECE, EEE", "C, Embedded C", 0, 2026, 65, 25, "Firmware development for IoT products."),
    ("Infiniti Software", "Associate Software Engineer", 4.2, "Full-time", 6.0, "CSE, IT, ECE, EEE", "Java, SQL", 2, 0, 0, 40, "Join a mentoring-based training programme and work on client projects."),
    ("Infiniti Software", "Java Full Stack Developer", 6.5, "Full-time", 7.5, "CSE, IT", "Java, JavaScript, SQL, HTML", 0, 2026, 60, 35, "Develop end-to-end features with Java and modern front ends."),
    ("Infiniti Software", "Technical Support Trainee", 3.2, "Full-time", 6.0, "All", "SQL", 3, 0, 0, 28, "First-line support for enterprise software customers."),
    ("BrightPath Digital", "Front-end Developer", 5.5, "Full-time", 7.0, "CSE, IT, AI&DS", "HTML, CSS, JavaScript", 0, 0, 0, 33, "Build landing pages and single-page apps for startups."),
    ("BrightPath Digital", "Web Developer Intern", 2.4, "Internship", 6.0, "All", "HTML, CSS", 2, 0, 0, 18, "Three-month paid internship on live client websites."),
    ("BrightPath Digital", "Python Backend Developer", 6, "Full-time", 7.0, "CSE, IT", "Python, SQL, Git", 0, 2026, 0, 38, "Create REST APIs and database models in Python."),
    ("DataCrest Analytics", "Data Analyst", 6, "Full-time", 7.5, "CSE, IT, AI&DS", "Python, SQL", 0, 0, 60, 30, "Turn client data into reports and dashboards."),
    ("DataCrest Analytics", "Business Intelligence Intern", 3.6, "Internship", 7.0, "CSE, IT, AI&DS, ECE", "SQL", 1, 0, 0, 16, "Support BI developers with data cleaning and visuals."),
    ("DataCrest Analytics", "Junior Data Engineer", 7, "Full-time", 8.0, "CSE, IT, AI&DS", "Python, SQL, Git", 0, 2026, 65, 45, "Maintain ETL pipelines for analytics clients."),
    ("NovaCloud Systems", "Cloud Support Engineer", 5.2, "Full-time", 7.0, "CSE, IT, ECE", "Python, Git", 1, 0, 0, 27, "Troubleshoot customer cloud environments."),
    ("NovaCloud Systems", "DevOps Trainee", 6.2, "Full-time", 7.5, "CSE, IT", "Python, Git, SQL", 0, 2026, 60, 42, "Learn CI/CD, containers and monitoring on the job."),
    ("SecureNet Labs", "Security Analyst Trainee", 6.8, "Full-time", 7.5, "CSE, IT, ECE", "Python, Networking", 0, 0, 60, 36, "Monitor alerts and investigate security incidents."),
    ("SecureNet Labs", "Penetration Testing Intern", 3.5, "Internship", 7.0, "CSE, IT", "Python, Linux", 0, 0, 0, 21, "Assist senior testers with web application assessments."),
    ("PixelForge Studios", "UI Developer", 5, "Full-time", 6.8, "CSE, IT, AI&DS", "HTML, CSS, JavaScript", 1, 0, 0, 24, "Turn design mockups into accessible interfaces."),
    ("PixelForge Studios", "UX Research Intern", 2.2, "Internship", 6.0, "All", "", 2, 0, 0, 14, "Run user interviews and usability tests."),
    ("Voltix Electronics", "Electrical Design Engineer", 5.6, "Full-time", 7.0, "EEE, ECE", "AutoCAD", 0, 2026, 60, 32, "Design control panels and wiring layouts."),
    ("Voltix Electronics", "PLC Automation Engineer", 6.2, "Full-time", 7.2, "EEE, ECE, MECH", "PLC, SCADA", 0, 0, 60, 29, "Program and commission automation lines."),
    ("Orbit Telecom", "Network Engineer", 5.8, "Full-time", 7.0, "ECE, EEE, CSE, IT", "Networking", 1, 0, 0, 31, "Plan and maintain regional telecom networks."),
    ("Orbit Telecom", "RF Test Engineer", 6.5, "Full-time", 7.5, "ECE", "RF, MATLAB", 0, 2026, 65, 37, "Test radio equipment before field deployment."),
    ("GreenGrid Energy", "Graduate Engineer Trainee", 4.8, "Full-time", 6.5, "EEE, MECH, CIVIL", "AutoCAD", 1, 0, 0, 26, "Rotational programme across solar and wind projects."),
    ("Titan Mechanical Works", "Design Engineer", 5.4, "Full-time", 7.0, "MECH", "AutoCAD, SolidWorks", 0, 2026, 60, 34, "Create 3D models and drawings for auto components."),
    ("Titan Mechanical Works", "Production Trainee", 3.8, "Full-time", 6.0, "MECH, EEE", "", 3, 0, 0, 19, "Supervise shop-floor production and quality checks."),
    ("BuildRight Constructions", "Site Engineer", 4.5, "Full-time", 6.5, "CIVIL", "AutoCAD", 1, 0, 0, 23, "Oversee site work, measurements and progress reports."),
    ("BuildRight Constructions", "Structural Design Intern", 2.5, "Internship", 7.0, "CIVIL", "STAAD Pro", 0, 0, 0, 17, "Assist with structural analysis and drawings."),
    ("FinEdge Payments", "Software Engineer", 9, "Full-time", 8.0, "CSE, IT", "Java, SQL, Git", 0, 2026, 70, 40, "Build high-volume payment services."),
    ("FinEdge Payments", "QA Automation Trainee", 5.5, "Full-time", 7.0, "CSE, IT, ECE", "Python, SQL", 0, 0, 0, 28, "Automate API and UI tests for payment flows."),
    ("CareLink Health Tech", "Software Developer", 6.4, "Full-time", 7.2, "CSE, IT, AI&DS", "Python, JavaScript, SQL", 0, 0, 60, 35, "Build patient-record and appointment features."),
    ("EduSpark Learning", "Full Stack Developer", 5.8, "Full-time", 7.0, "CSE, IT", "JavaScript, HTML, CSS, SQL", 1, 0, 0, 30, "Develop course and assessment modules."),
    ("EduSpark Learning", "Content Technology Intern", 2.0, "Internship", 6.0, "All", "HTML", 2, 0, 0, 12, "Prepare interactive learning content."),
    ("SwiftCart Commerce", "Backend Developer", 8, "Full-time", 7.8, "CSE, IT", "Java, SQL, Git", 0, 2026, 65, 38, "Scale order and inventory services."),
    ("SwiftCart Commerce", "Operations Analyst", 4.6, "Full-time", 6.5, "All", "SQL", 2, 0, 0, 25, "Analyse delivery data and improve logistics KPIs."),
    ("QuantumLeap AI", "Machine Learning Engineer", 10, "Full-time", 8.5, "CSE, IT, AI&DS", "Python, SQL", 0, 2026, 70, 45, "Train and deploy computer vision models."),
    ("QuantumLeap AI", "AI Research Intern", 4, "Internship", 8.0, "CSE, IT, AI&DS", "Python", 0, 0, 0, 20, "Prototype models with a research team."),
    ("Apex Global Services", "Customer Support Associate", 3, "Full-time", 6.0, "All", "", 3, 0, 0, 21, "Handle technical queries for international customers."),
    ("Apex Global Services", "Process Analyst (Part-time)", 2.4, "Part-time", 6.0, "All", "", 2, 0, 0, 13, "Evening-shift analysis and reporting role."),
]


def main():
    if not os.path.exists(DB):
        raise SystemExit("placement_management.db not found. Run `python app.py` once first.")
    db = sqlite3.connect(DB)
    db.execute("PRAGMA foreign_keys = ON")
    new_companies = new_jobs = 0
    ids = {}
    for name, (desc, site, loc) in COMPANIES.items():
        row = db.execute("SELECT id FROM companies WHERE company_name=?", (name,)).fetchone()
        if row:
            ids[name] = row[0]
        else:
            ids[name] = db.execute(
                "INSERT INTO companies(company_name,description,website,location) VALUES(?,?,?,?)",
                (name, desc, site, loc)).lastrowid
            new_companies += 1
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for (co, role, sal, jtype, cgpa, depts, skills, backlogs, year, pct, days, desc) in JOBS:
        cid = ids[co]
        if db.execute("SELECT 1 FROM jobs WHERE company_id=? AND job_role=?", (cid, role)).fetchone():
            continue
        db.execute(
            """INSERT INTO jobs(company_id,job_role,salary,job_type,minimum_cgpa,required_department,required_skills,
               maximum_backlogs,graduation_year,min_percentage,deadline,description,is_active,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
            (cid, role, sal, jtype, cgpa, depts, skills, backlogs, year, pct,
             (date.today() + timedelta(days=days)).isoformat(), desc, stamp))
        new_jobs += 1
    if new_jobs:
        db.execute("INSERT INTO notifications(student_id,title,message,created_at) SELECT id,?,?,? FROM students",
                   ("New job postings", f"{new_jobs} new jobs were added. Open Find Jobs to see the ones you qualify for.", stamp))
    db.commit()
    db.close()
    print(f"Added {new_companies} companies and {new_jobs} jobs.")


if __name__ == "__main__":
    main()
