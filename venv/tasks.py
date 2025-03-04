import os
from datetime import datetime
from models import History
from celery_app import celery, flask_app
from file_to_solution import image_to_pdf, latex_solution, latex_to_pdf
from redis import Redis
from config import Config 
from models  import History,db
from app import create_app
redis_client = Redis(
    host=Config.REDIS_HOST,
    port=Config.REDIS_PORT,
    db=Config.REDIS_DB
)
@celery.task
def process_file_task(filename):
    """Convert image to PDF and track status in Redis."""
    with flask_app.app_context():
        from models import db, History
        

        redis_key = f"file:{filename}"
        try:
            upload_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], filename)
            
            # Update Redis status to "processing"
            redis_client.hset(redis_key, "status", "processing")
            
            # Convert image to PDF
            output_pdf = image_to_pdf(upload_path)
            pdf_filename = os.path.basename(output_pdf)
            
            # Update Redis with success status and PDF name
            redis_client.hset(redis_key, "status", "completed")
            redis_client.hset(redis_key, "pdf_filename", pdf_filename)
            filename=os.path.splitext(filename)[0]
            
            # Remove original file
            os.remove(upload_path)
            
        except Exception as e:
            # Log error and update Redis
            error_msg = f"Error processing {filename}: {str(e)}"
            print(error_msg)
            redis_client.hset(redis_key, "status", "failed")
            redis_client.hset(redis_key, "error", error_msg)
            
        finally:
            # Auto-clean Redis data after 1 hour
            redis_client.expire(redis_key, 3600)
@celery.task
def process_solution_program_task(base_name,user_id):
    """Generate solution PDF with Redis status tracking"""
    with flask_app.app_context():
        
        redis_key = f"solution:{base_name}"
        try:
            redis_client.hset(redis_key, "status", "processing")
            
            tex_path = os.path.join(flask_app.config['TEX_FOLDER'], f"{base_name}.tex")
            grade = latex_solution(tex_path)
            
            solution_tex = os.path.join(flask_app.config['TEX_FOLDER'], f"{base_name}_solution.tex")
            latex_to_pdf(solution_tex)
            
            pdf_filename = f"{base_name}_solution.pdf"
            redis_client.hmset(redis_key, {
                "status": "completed",
                "grade": str(grade),
                "pdf_filename": pdf_filename
            })
            new_history = History(
                filename=os.path.splitext(base_name)[0],
                original_pdf=pdf_filename.replace("_solution", ""),
                timestamp=datetime.now(),
                grade=grade,
                solution_pdf=pdf_filename,
                user_id=user_id
            )
            db.session.add(new_history)
            db.session.commit()
        except Exception as e:
            redis_client.hmset(redis_key, {
                "status": "failed",
                "error": str(e)
            })
            flask_app.logger.error(f"Solution error for {base_name}: {e}")
        finally:
            redis_client.expire(redis_key, 3600)
            