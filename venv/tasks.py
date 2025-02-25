import os
import time
from celery_app import celery, flask_app
from file_to_solution import image_to_pdf, latex_solution, latex_to_pdf

@celery.task
def process_file_task(filename):
    """Convert image to PDF and remove the original file."""
    with flask_app.app_context():
        try:
            pdf_filename = f"{os.path.splitext(filename)[0]}.pdf"
            # Convert image to PDF
            upload_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], filename)
            image_to_pdf(upload_path)

            # Remove the original uploaded file
            os.remove(upload_path)
        except Exception as e:
            print(f"Error in process_file_task: {e}")

@celery.task
def process_solution_program_task(base_name):
    """Generate a solution PDF from a LaTeX file."""
    with flask_app.app_context():
        try:
            tex_filename = f"{base_name}.tex"
            tex_path = os.path.join(flask_app.config['TEX_FOLDER'], tex_filename)
            print(f"[tasks] Processing solution for: {tex_path}")
            
            # Generate solution .tex file
            solution_tex = latex_solution(tex_path)
            print(f"[tasks] Returned solution file path: {solution_tex}")
            
            # Check if the file exists
            if not os.path.exists(solution_tex):
                flask_app.logger.error("Solution file was not created: " + solution_tex)
                return
            
            # Convert solution .tex file to PDF
            pdf_result = latex_to_pdf(solution_tex)
            print(f"[tasks] PDF conversion result: {pdf_result}")
            
        except Exception as e:
            flask_app.logger.error(f"Error in process_solution_program_task: {e}", exc_info=True)
