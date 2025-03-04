from flask import Flask, render_template, request, session, flash, redirect, url_for, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import logging
from werkzeug.utils import secure_filename
import subprocess
from redis import Redis
from config import Config
from models import Users, History,db
redis_client=Redis(
    host=Config.REDIS_HOST,
    port=Config.REDIS_PORT,
    db=Config.REDIS_DB
)
def create_app():
    """Factory to create the Flask app."""
    app = Flask(__name__)
    app.secret_key = "replace_with_a_secret_key"
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    # --- Config ---
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.sqlite3'
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
    app.config['PDF_FOLDER'] = os.path.join(BASE_DIR, 'static', 'pdfs')
    app.config['TEX_FOLDER'] = os.path.join(BASE_DIR, 'static', 'tex')    
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    db.init_app(app)

    # Ensure these directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['PDF_FOLDER'], exist_ok=True)
    os.makedirs(app.config['TEX_FOLDER'], exist_ok=True)

    
    def allowed_file(filename):
        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    @app.context_processor
    def inject_user():
        user = None
        if 'email' in session:
            found_user = Users.query.filter_by(email=session['email']).first()
            if found_user:
                user = found_user.username
        return {'user': user}

    # ---------------- ROUTES ----------------
    @app.route('/')
    def home():
        user = None
        if 'email' in session:
            found_user = Users.query.filter_by(email=session['email']).first()
            if found_user:
                user = found_user.username
        return render_template('index.html', user=user)
    @app.route('/history')
    def history():
        if 'email' not in session:
            return redirect(url_for('login'))
        user = Users.query.filter_by(email=session['email']).first()
        if not user:
            return redirect(url_for('login'))
        entries = History.query.filter_by(user_id=user._id).order_by(History.timestamp.desc()).all()
        return render_template('history.html', entries=entries)
    @app.route('/login', methods=['POST', 'GET'])
    def login():
        if request.method == 'POST':
            user = request.form['email']
            password = request.form['password']
            found_user = Users.query.filter_by(email=user).first()
            if found_user:
                if found_user.password == password:
                    session['email'] = user
                    return redirect(url_for('home'))
                else:
                    flash('Mot de passe incorrect')
            else:
                flash('Utilisateur inconnu , veuillez vous inscrire')
            return redirect(url_for('login'))
        return render_template('login.html')

    @app.route('/register', methods=['POST', 'GET'])
    def register():
        if request.method == 'POST':
            us = request.form['username']
            user = request.form['email']
            password = request.form['password']
            if Users.query.filter_by(email=user).first():
                flash('Utilisateur existe déjà')
                return redirect(url_for('register'))
            new_user = Users(us, user, password)
            db.session.add(new_user)
            db.session.commit()
            flash('Bienvenue')
            return redirect(url_for('login'))
        return render_template('register.html')

    @app.route('/logout')
    def logout():
        session.pop('email', None)
        return redirect(url_for('home'))

    @app.route("/upload", methods=["POST", "GET"])
    def upload():
        from tasks import process_file_task
        if request.method == "POST":
            if 'file' not in request.files:
                flash('No file part')
                return redirect(url_for('upload'))
            files = request.files.getlist('file')
            saved_filenames = []

            for file in files:
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    try:
                        file.save(file_path)
                        process_file_task.delay(filename)
                        saved_filenames.append(filename)
                    except Exception as e:
                        flash(f"Error saving {filename}: {str(e)}")

            if saved_filenames:
                session['uploaded_files'] = saved_filenames
                return redirect(url_for('processing', filenames=','.join(saved_filenames)))
            else:
                flash('No valid files processed')
                return redirect(url_for('upload'))
        return render_template('upload.html')
    @app.route("/processing/<filenames>")
    def processing(filenames):
        filename_list = filenames.split(',')
        return render_template("processing.html", filenames=filename_list)
    @app.route("/display_pdf/<filename>")
    def display_pdf(filename):
        file_list = session.get('uploaded_files', [])
        try:
            current_index = file_list.index(filename)
        except ValueError:
            current_index = -1
        
        # Calculate indices with 2-file steps
        prev_index = current_index - 1
        next_index = current_index + 1
        
        prev_file = file_list[prev_index] if prev_index >= 0 else None
        next_file = file_list[next_index] if next_index < len(file_list) else None
        
        return render_template("display_pdf.html",
                            pdf_filename=filename,
                            prev_file=prev_file,
                            next_file=next_file,
                            file_index=current_index + 1,
                            total_files=len(file_list))  
    @app.route("/check_file/<filename>")
    def check_file(filename):
        redis_key = f"file:{filename}"
        file_data = redis_client.hgetall(redis_key)
        
        if file_data:
            status = file_data.get(b"status", b"").decode()
            if status == "completed":
                pdf_filename = file_data.get(b"pdf_filename", b"").decode()
                return jsonify({
                    "ready": True,
                    "url": url_for('display_pdf', filename=os.path.splitext(pdf_filename)[0]+'.pdf')
                })
            elif status == "failed":
                error = file_data.get(b"error", b"Unknown error").decode()
                return jsonify({"ready": False, "error": error})
        
        # Fallback: Check filesystem if Redis data is missing
        original_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        pdf_filename = f"{os.path.splitext(filename)[0]}.pdf"
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        if os.path.exists(pdf_path):
            return jsonify({"ready": True, "url": url_for('display_pdf', filename=pdf_filename)})
        elif os.path.exists(original_path):
            return jsonify({"ready": False})
        else:
            return jsonify({"ready": False, "error": "File not found"})
    @app.route('/get_grade/<base_name>')
    def get_grade(base_name):
        grade = redis_client.hget(f"grades:{base_name}","grade")
        pdf_filename=redis_client.hget(f"grades:{base_name}","pdf_filename")
        if grade and pdf_filename:
            return jsonify({
                "ready": True, 
                "grade": grade.decode(), 
                "pdf_filename": pdf_filename.decode()
            })
        else:
            return jsonify({"ready": False})

    @app.route('/download/<filename>')
    def download_pdf(filename):
        return send_from_directory(
            app.config['PDF_FOLDER'],
            filename,
            as_attachment=True
        )

    @app.route("/validate/<filename>", methods=["GET"])
    def validate(filename):
        tex_filename = os.path.splitext(filename)[0] + ".tex"
        tex_path = os.path.join(app.config['TEX_FOLDER'], tex_filename)
        if not os.path.exists(tex_path):
            flash("LaTeX file not found for validation.")
            return redirect(url_for('home'))
        with open(tex_path, "r") as f:
            latex_code = f.read()
        return render_template("validate.html", filename=filename, latex_code=latex_code)

    @app.route("/compile_tex/<filename>", methods=["POST"])
    def compile_tex(filename):
        edited_code = request.form.get("latex_code")
        if not edited_code:
            flash("No LaTeX code submitted.")
            return redirect(url_for('validate', filename=filename))
        
        tex_filename = os.path.splitext(filename)[0] + ".tex"
        tex_path = os.path.join(app.config['TEX_FOLDER'], tex_filename)
        # Write the edited LaTeX code back to the file
        with open(tex_path, "w") as f:
            f.write(edited_code)
        try:
            # Run pdflatex in the TEX_FOLDER
            subprocess.run(["pdflatex", "-interaction=nonstopmode", tex_filename],
                        cwd=app.config['TEX_FOLDER'], check=True)
            # Move generated PDF to PDF_FOLDER
            generated_pdf = os.path.splitext(tex_filename)[0] + ".pdf"
            src_pdf = os.path.join(app.config['TEX_FOLDER'], generated_pdf)
            dest_pdf = os.path.join(app.config['PDF_FOLDER'], generated_pdf)
            os.rename(src_pdf, dest_pdf)
            # Optionally, remove aux/log files
            for ext in [".aux", ".log"]:
                aux_file = os.path.join(app.config['TEX_FOLDER'], f"{os.path.splitext(tex_filename)[0]}{ext}")
                if os.path.exists(aux_file):
                    os.remove(aux_file)
            return redirect(url_for('display_pdf', filename=generated_pdf))
        except subprocess.CalledProcessError as e:
            flash("Error compiling LaTeX. Please check your code.")
            return redirect(url_for('validate', filename=filename))

    @app.route("/processing_solution/<filename>")
    def processing_solution(filename):
        return render_template("processing_solution.html", filename=filename)

    @app.route('/solution_pdf/<filename>')
    def solution_pdf(filename):
        if 'email' not in session:
            return redirect(url_for('login'))
        user = Users.query.filter_by(email=session['email']).first()
        if not user:
            return redirect(url_for('login'))
        from tasks import process_solution_program_task
        safe_filename = secure_filename(filename)
        base_name = os.path.splitext(safe_filename)[0]
        process_solution_program_task.delay(base_name,user._id)
        return redirect(url_for('processing_solution', filename=safe_filename.replace(".pdf","_solution.pdf")))
    @app.route('/solution/<filename>')
    def solution(filename):
        base_name = os.path.splitext(filename)[0].replace("_solution", "")
        history_entry = History.query.filter_by(filename=base_name).first()
        if history_entry:
            grade_value = history_entry.grade
        else:
            grade_value = "Not graded"
        
        # Get solution files list
        uploaded_files = session.get('uploaded_files', [])
        solution_files = [f"{os.path.splitext(f)[0]}_solution.pdf" for f in uploaded_files]
        
        try:
            current_index = solution_files.index(filename)
        except ValueError:
            current_index = -1
        
        # Calculate indices with 2-file steps
        prev_index = current_index - 1
        next_index = current_index + 1
        
        prev_file = solution_files[prev_index] if prev_index >= 0 else None
        next_file = solution_files[next_index] if next_index < len(solution_files) else None
        
        return render_template("solution_pdf.html",
                            filename=filename,
                            grade=grade_value,
                            prev_file=prev_file,
                            next_file=next_file,
                            file_index=current_index + 1,
                            total_files=len(solution_files))    
    @app.route("/check_solution/<filename>")
    def check_solution(filename):
        solution_pdf_file = secure_filename(filename)
        pdf_path = os.path.join(app.config['PDF_FOLDER'], solution_pdf_file)
        if os.path.exists(pdf_path):
            return jsonify({
                "ready": True,
                "url": url_for('solution', filename=f'{solution_pdf_file}')
            })
        else:
            return jsonify({"ready": False})

        

    @app.route('/process_all_solutions', methods=['POST'])
    def process_all_solutions():
        """Trigger solution generation for all processed files"""
        from tasks import process_solution_program_task
        if 'email' not in session:
            return redirect(url_for('login'))
        user = Users.query.filter_by(email=session['email']).first()
        if not user:
            return redirect(url_for('login'))

        # Get all base names from the TEX_FOLDER
        tex_files = [f for f in os.listdir(app.config['TEX_FOLDER']) if f.endswith('.tex')]
        base_names = [os.path.splitext(f)[0] for f in tex_files if '_solution' not in f]
        
        # Start solution tasks for all files
        for base_name in base_names:
            process_solution_program_task.delay(base_name, user._id)
        
        return jsonify({
            "message": f"Started solution generation for {len(base_names)} files",
            "files": base_names
        })
    @app.route('/delete_history/<int:entry_id>', methods=['POST'])
    def delete_history(entry_id):
        if 'email' not in session:
            return redirect(url_for('login'))
        
        user = Users.query.filter_by(email=session['email']).first()
        if not user:
            return redirect(url_for('login'))
        
        entry = History.query.get_or_404(entry_id)
        
        # Verify ownership
        if entry.user_id != user._id:
            flash("Accès non autorisé")
            return redirect(url_for('history'))
        
        try:
            db.session.delete(entry)
            db.session.commit()
            flash("Entrée supprimée avec succès")
        except Exception as e:
            db.session.rollback()
            flash("Erreur lors de la suppression")
    
        return redirect(url_for('history'))
    @app.route('/check_all_solutions')
    def check_all_solutions():
        """Check status of all solution generations"""
        tex_files = [f for f in os.listdir(app.config['TEX_FOLDER']) if f.endswith('.tex')]
        base_names = [os.path.splitext(f)[0] for f in tex_files if '_solution' not in f]
        
        statuses = {}
        for base_name in base_names:
            redis_key = f"solution:{base_name}"
            data = redis_client.hgetall(redis_key)
            statuses[base_name] = {
                "status": data.get(b"status", b"pending").decode(),
                "grade": data.get(b"grade", b"").decode(),
                "pdf_filename": data.get(b"pdf_filename", b"").decode(),
                "error": data.get(b"error", b"").decode()
            }
        
        return jsonify(statuses)
    return app

# --- Main (so you can still run via python app.py) ---
if __name__ == '__main__':
    # Create the Flask app and DB
    flask_app = create_app()
    with flask_app.app_context():
        db.create_all()

    # Start the dev server
    flask_app.run(debug=True)
