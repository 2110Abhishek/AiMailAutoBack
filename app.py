from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import fitz
import re
from jinja2 import Template
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import time

app = Flask(__name__)
CORS(app)

uploads = {}
stop_flags = {}

@app.route('/upload', methods=['POST'])
def upload_files():
    pdf_file = request.files['pdf']
    template_file = request.files['template']
    resume_file = request.files['resume']

    sender_email = request.form['senderEmail']
    sender_password = request.form['senderPassword']
    position = request.form['position']

    pdf_path = "contacts.pdf"
    template_path = "template.txt"
    resume_path = "resume.pdf"

    pdf_file.save(pdf_path)
    template_file.save(template_path)
    resume_file.save(resume_path)

    uploads[sender_email] = {
        "pdf": pdf_path,
        "template": template_path,
        "resume": resume_path,
        "password": sender_password,
        "position": position
    }

    stop_flags[sender_email] = False

    return jsonify({"message": "Files uploaded. Sending will begin..."})

@app.route('/stop-sending', methods=['GET'])
def stop_sending():
    sender_email = request.args.get('senderEmail')
    stop_flags[sender_email] = True
    return jsonify({"message": "Stopping email sending..."})

@app.route('/send-emails', methods=['GET'])
def send_emails():
    sender_email = request.args.get('senderEmail')
    if sender_email not in uploads:
        return jsonify({"error": "No upload found for this sender."}), 400

    info = uploads[sender_email]
    doc = fitz.open(info["pdf"])
    email_set = set()
    for page in doc:
        text = page.get_text()
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        email_set.update(emails)

    with open(info["template"], encoding='utf-8') as f:
        template_content = f.read()

    template = Template(template_content)
    rendered_email = template.render(name="HR", position=info["position"])

    def generate():
        for to_email in email_set:
            if stop_flags.get(sender_email):
                yield f"data: Sending stopped by user.\n\n"
                print(f"Sending stopped by user: {sender_email}")
                break

            msg = MIMEMultipart()
            msg["Subject"] = f"Application for {info['position']} Position"
            msg["From"] = sender_email
            msg["To"] = to_email

            msg.attach(MIMEText(rendered_email, "plain", "utf-8"))

            with open(info["resume"], "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename=resume.pdf")
                msg.attach(part)

            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(sender_email, info["password"])
                    server.sendmail(sender_email, to_email, msg.as_string())
                print(f"Sent to {to_email}")
                yield f"data: Sent to {to_email}\n\n"
            except Exception as e:
                print(f"Error sending to {to_email}: {e}")
                yield f"data: Failed to send to {to_email}: {e}\n\n"

            time.sleep(0.5)

        os.remove(info["pdf"])
        os.remove(info["template"])
        os.remove(info["resume"])
        uploads.pop(sender_email, None)
        stop_flags.pop(sender_email, None)
        yield f"data: DONE\n\n"

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)

