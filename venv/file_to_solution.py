from openai import OpenAI
import base64
import json
from dotenv import load_dotenv
import subprocess
import os
import re
import PyPDF2
from celery_app import flask_app
load_dotenv()  
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = OpenAI(
  api_key=OPENAI_API_KEY
)

def encode_image(image_path):
    with open(image_path, "rb") as image:
        return base64.b64encode(image.read()).decode('utf-8')

def image_to_text(image_path):
    try:
        if image_path.lower().endswith('.pdf'):
            # Read PDF file
            pdf_reader = PyPDF2.PdfReader(image_path)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": (f"Convert this text to LaTeX code. Include these packages:\n"
                                "\\usepackage[utf8]{inputenc}\n"
                                "\\usepackage[T1]{fontenc}\n"
                                "\\usepackage{amsmath}\n"
                                "\\usepackage{amssymb}\n"
                                "Return ONLY raw LaTeX code with document structure."
                                f"Text to convert:\n{text}")
                }]
            )
        else:
            image = encode_image(image_path)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": ("Convert to LaTeX code. Include these packages:\n"
                                     "\\usepackage[utf8]{inputenc}\n"
                                     "\\usepackage[T1]{fontenc}\n"
                                     "\\usepackage{amsmath}\n"
                                     "\\usepackage{amssymb}\n"
                                     "Return ONLY raw LaTeX code with document structure.")
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image}"
                            }
                        }
                    ]
                }]
            )
        latex_code = response.choices[0].message.content
        return _clean_latex_code(latex_code)
    
    except Exception as e:
        return str(e)

def _clean_latex_code(code):
    """Sanitize the LaTeX output from GPT"""
    # Ensure basic font encoding is specified
    code = re.sub(r'\\begin{document}', r'''\\usepackage[utf8]{inputenc}
\\usepackage[T1]{fontenc}
\\begin{document}''', code)
    # Remove markdown code blocks
    code = re.sub(r'```(latex)?', '', code)
    # Preserve document class and packages
    code = re.sub(r'^.*?(\\documentclass)', r'\1', code, flags=re.DOTALL)
    return code.strip()

def image_to_pdf(image_path):
    try:
        output_path = "static/pdfs/" + os.path.basename(image_path)
        os.makedirs("static/pdfs", exist_ok=True)
        os.makedirs("static/tex", exist_ok=True)
        
        # Get LaTeX code from image
        latex_code = image_to_text(image_path)
        tex_file = os.path.join("static/tex", os.path.splitext(os.path.basename(image_path))[0] + ".tex")
        with open(tex_file, "w") as f:
            f.write(latex_code)
        
        subprocess.run(["pdflatex", "-interaction=nonstopmode","-output-directory=../pdfs", os.path.basename(tex_file)], cwd="static/tex")
        for ext in [".log", ".aux"]:
            aux_file = os.path.join("static/pdfs", f"{os.path.splitext(os.path.basename(tex_file))[0]}{ext}")
            if os.path.exists(aux_file):
                os.remove(aux_file)
        print(f"PDF generated: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Error generating PDF: {e}")
        return f"Error generating PDF: {str(e)}"
    except Exception as e:
        print(f"Error: {e}")
        return f"Error: {str(e)}"

def latex_solution(filename):
    try:
        with open(filename, 'r') as file:
            latex_content = file.read()
        print("\n[latex_solution] Read original LaTeX content from:", filename)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", 
                 "content": (
                     "You are a teacher. Here's a math copy in LaTeX. Please correct it and give recommandations for the student. "
                     "Give the student's answer and the correct answer if the student is wrong. "
                     "Give a grade for every question and a grade for all. "
                     "It is in French so the answer should be in French. "
                     "If the answer is incomplete or unjustified, give the missing part and don't give the full grade "
                     "The grade should be /20."
                     "Give a scale of 20 for the whole copy. "
                     "Give the grade for every question and the grade for all. "
                     "Remove points if the student is wrong or if the answer is incomplete or if the answer is not justified."
                     "If the answer is incorrect , give 0 and give the corrected answer"
                     "Be more severe in your correction."
                     "If they don't give justification, remove points."
                     "write in color red to the correction you added"
                     "And provide the solution in LaTeX format, don't add any other text:\n\n" + latex_content
                 )}
            ]
        )
        solution = response.choices[0].message.content
        solution = _clean_latex_code(solution)
        pattern = r'(\d+\.?\d*)\s*/\s*20'
        match=re.search(pattern,solution)
        if match:
            grade=match.group(0)
        solution_filename = f"static/tex/{os.path.basename(filename).replace('.tex', '_solution.tex')}"
        with open(solution_filename, 'w') as f:
            f.write(solution)
        print(f"[latex_solution] Written solution file: {solution_filename}")
        return grade
    except Exception as e:
        print(f"[latex_solution] Error: {e}")
        return f"Error: {str(e)}"

def latex_to_pdf(tex_file):
    try:
        output_dir = flask_app.config['PDF_FOLDER']
        tex_dir = flask_app.config['TEX_FOLDER']
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(tex_dir, exist_ok=True)
        
        tex_file_basename = os.path.basename(tex_file)
        print(f"[latex_to_pdf] Running pdflatex on: {tex_file_basename} in directory: {tex_dir}")
        
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode","-output-directory=../pdfs", tex_file_basename],
            cwd=tex_dir
        )
        pdf_name = os.path.splitext(tex_file_basename)[0] + ".pdf"
        src_pdf = os.path.join(tex_dir, pdf_name)
        dest_pdf = os.path.join(output_dir, pdf_name)   
        for ext in [".aux", ".log"]:
            aux_file = os.path.join(output_dir, f"{os.path.splitext(pdf_name)[0]}{ext}")
            if os.path.exists(aux_file):
                os.remove(aux_file)
                
        print(f"[latex_to_pdf] Solution PDF generated: {dest_pdf}")
        return dest_pdf
    except Exception as e:
        print(f"[latex_to_pdf] Error generating solution PDF: {e}")
        return str(e)
