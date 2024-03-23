import os
import ocrmypdf
import re
import PyPDF2
import pandas as pd
import cv2
from pdf2image import convert_from_path
import shutil
from os import listdir
from os.path import isfile, join
from datetime import datetime
import locale

# define all the list of document you want to scan in this list
ocr_file_list = ["SMUCPRN0222111517220", "SMUCPRN0222111517430", "SMUCPRN0222111517240",
                 "SMUCPRN0222111517350", "SMUCPRN0222111517290"]

# define the document split markers which define the beginning of new document
START_TEXT = ["Protokoll", "Einladung", "Anwesenheitsliste"]

# define the document split markers which define the end of a document
END_TEXT = ["mit corpsbrider", "mit corpsbriider", "mit freundlichen", "mit freundlichem", "Ende der Sitzung",
            "Schluss der Sitzung", "gez.", "Mit corpsbruder", "anlagen:", "anlage:", "anlagen.", "anlage.",
            "anlagen ", "anlage ", "anhang "]

# Define City name as 'City, Date' pattern, this helps us fine the city,
# date pattern which marks start of a new document
city_date_text = ["Munchen", "Miinchen", "Mtinchen", "Minchen"]


# define the operations you want to perform, mark the variables as True or False
REMOVE_BLANK_PAGES = True
CONVERT_SCANNED_DOC_TO_PDF = True
SPLIT_PDF_DOCS = True
NAME_SPLITTED_DOCS = True
CONVERT_PDF_TO_IMAGE = False
SPLIT_MACHINE_HANDWRITTEN_TEXTS = False


date_pattern = r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|(?:\d{1,2} )?(?:Jan(?:uar)?|Feb(?:ruar)?|Mär(?:z)?|Apr(?:il)?|Mai|Jun(?:i)?|Jul(?:i)?|Aug(?:ust)?|Sep(?:tember)?|Okt(?:ober)?|Nov(?:ember)?|Dez(?:ember)?) [0-9]+,? \d{4}|\d{1,2}\. (?:Jan(?:uar)?|Feb(?:ruar)?|Mär(?:z)?|Apr(?:il)?|Mai|Jun(?:i)?|Jul(?:i)?|Aug(?:ust)?|Sep(?:tember)?|Okt(?:ober)?|Nov(?:ember)?|Dez(?:ember)?) \d{4}|\d{1,2}\.\d{1,2}\.\d{4}'


def convert_pdf_to_images():
    # Convert a PDF page to an image
    images = convert_from_path('stg_20/SMUCPRN0222111517290_brewed.pdf')
    for i in range(0, 50):
        images[i].save(f'pdf_images/SMUCPRN0222111517290_image_{i}.jpg', 'JPEG')


def split_machine_handwritten_pdf():
    threshold = 2
    threshold_area = 100
    threshold_vertices = 10

    image = cv2.imread(f'pdf_images/SMUCPRN0222111517290_image_0.jpg')
    # Convert the image to grayscale
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Apply binary thresholding to create a binary image
    _, binary_image = cv2.threshold(gray_image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Apply noise reduction (optional)
    binary_image = cv2.medianBlur(binary_image, 3)

    # Find contours in the binary image
    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    #Visualize the image with edges
    #cv2.imshow('Image with contours', binary_image)
    #cv2.waitKey(0)
    #cv2.destroyAllWindows()

    # Iterate through the contours and analyze them for irregular shapes
    for contour in contours:
        # Calculate the area of the contour
        area = cv2.contourArea(contour)

        # Filter out small noise
        if area < threshold_area:
            continue

        # Approximate the contour to a polygon (simplify)
        epsilon = 0.04 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        # Analyze the number of vertices (indicative of shape complexity)
        if len(approx) < threshold_vertices:
            # This contour represents an irregular shape (potentially handwritten)
            cv2.drawContours(image, [contour], -1, (0, 0, 255), 2)  # Draw a red border around it
            print("Handwritten text")
        else:
            print("Machine text")


def stg_10_remove_blank_pages():
    """
    reads from input folder
    removes blank pages
    saves into stg_10 folder
    :return:
    """
    for files in ocr_file_list:
        filepath = "input/" + files + ".pdf"
        os.system(f"scanprep {filepath} stg_10")


def stg_20_generate_ocr_brewed_pdfs():
    """
    reads from stg_10 folder
    rotates, deskews and converts into readable pdf
    saves into stg_20 folder
    :return:
    """
    for ocr_file in ocr_file_list:
        ocr_file_brewed = "stg_20/" + ocr_file + "_brewed.pdf"
        ocr_file = "stg_10/0-" + ocr_file + ".pdf"
        ocrmypdf.ocr(ocr_file, ocr_file_brewed, deskew=True, rotate_pages=True)


def find_city_date_index(city_date_text, page_text):
    page_text = page_text[:500].lower()

    for substring in city_date_text:
        substring = substring.lower()
        # Find all occurrences of the substring in the text
        start_positions = [pos for pos in range(len(page_text)) if page_text.startswith(substring, pos)]

        # Extract the next 30 characters after each match
        for start_pos in start_positions:
            end_pos = start_pos + len(substring)
            next_30_chars = page_text[end_pos:end_pos + 30]

            doc_dates = re.findall(date_pattern, next_30_chars, re.IGNORECASE)
            if len(doc_dates) > 0:
                return True, substring + doc_dates[0]

    return False, None


def find_start_index(page_text, start_text):
    for start in start_text:
        if start.lower() in page_text[:1000].lower():
            return True, start.lower()
    return False, None


def find_end_index(page_text, end_text):
    for end in end_text:
        if end.lower() in page_text[-500:].lower():
            return True, end.lower()
    return False, None


def stg_30_split_pdf():
    """
    reads from stg_20 folder
    reads each page of pdf file and extracts the text
    matches the extracted text with split text
    if found then splits the pdf with a pdf file name
    :return:
    """
    start_text = START_TEXT
    end_text = END_TEXT

    df_stats = pd.DataFrame(columns=['page_number', 'split_text', 'output_pdf'])

    for ocr_file in ocr_file_list:
        split_pdf_output = "output/" + ocr_file
        input_pdf = "stg_20/" + ocr_file + "_brewed.pdf"

        with open(input_pdf, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(pdf_reader.pages)

            start_page = 0
            found_split = False
            split_reason = None
            last_split_page = -1

            for page_num in range(total_pages):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()

                if not found_split and page_num > 0 and page_num > last_split_page:
                    found_split, split_reason = find_start_index(page_text, start_text)
                    split = "before"

                if not found_split and page_num > 0 and page_num > last_split_page:
                    found_split, split_reason = find_city_date_index(city_date_text, page_text)
                    split = "before"

                if not found_split:
                    found_split, split_reason = find_end_index(page_text, end_text)
                    split = "after"

                if found_split:
                    if split == "after":
                        output_pdf = split_pdf_output + f'_split_{start_page + 1}-{page_num + 1}.pdf'
                        row = {'page_number': (page_num + 1), 'split_text': split_reason, 'output_pdf': output_pdf[7:]}
                        new_df = pd.DataFrame([row])
                        df_stats = pd.concat([df_stats, new_df], axis=0, ignore_index=True)
                        with open(output_pdf, 'wb') as output_file:
                            pdf_writer = PyPDF2.PdfWriter()
                            for i in range(start_page, page_num + 1):
                                pdf_writer.add_page(pdf_reader.pages[i])
                            pdf_writer.write(output_file)
                        last_split_page = page_num + 1
                        start_page = page_num + 1
                    elif split == "before":
                        output_pdf = split_pdf_output + f'_split_{start_page + 1}-{page_num}.pdf'
                        row = {'page_number': page_num, 'split_text': split_reason, 'output_pdf': output_pdf[7:]}
                        new_df = pd.DataFrame([row])
                        df_stats = pd.concat([df_stats, new_df], axis=0, ignore_index=True)
                        with open(output_pdf, 'wb') as output_file:
                            pdf_writer = PyPDF2.PdfWriter()
                            for i in range(start_page, page_num):
                                pdf_writer.add_page(pdf_reader.pages[i])
                            pdf_writer.write(output_file)
                        last_split_page = page_num
                        start_page = page_num

                found_split = False

            if start_page < total_pages:
                output_pdf = split_pdf_output + f'_split_{start_page + 1}-{total_pages}.pdf'
                row = {'page_number': (page_num + 1), 'split_text': split_reason, 'output_pdf': output_pdf[7:]}
                new_df = pd.DataFrame([row])
                df_stats = pd.concat([df_stats, new_df], axis=0, ignore_index=True)
                with open(output_pdf, 'wb') as output_file:
                    pdf_writer = PyPDF2.PdfWriter()
                    for i in range(start_page, total_pages):
                        pdf_writer.add_page(pdf_reader.pages[i])
                    pdf_writer.write(output_file)

    df_stats.to_csv("doc_split_info.csv", index=False)


# Function to convert any date format to yyyy-mm-dd
def convert_to_yyyy_mm_dd(input_date):
    # Set the locale to German
    locale.setlocale(locale.LC_TIME, 'de_DE')

    try:
        # Detect and parse the input date format
        date_formats = ["%d. %B %Y", "%d.%m.%Y", "%d. %B %Y", "%d. %B %Y", "%Y-%m-%d"]
        for date_format in date_formats:
            try:
                input_date = datetime.strptime(input_date, date_format)
                break
            except ValueError:
                pass

        # Format the date as yyyy-mm-dd
        yyyy_mm_dd_date = input_date.strftime("%Y-%m-%d")
        return yyyy_mm_dd_date
    except ValueError:
        return None
    except Exception:
        return None


def find_dates(page_text):
    date_match = re.findall(date_pattern, page_text, re.IGNORECASE)

    if date_match:
        date_formatted = convert_to_yyyy_mm_dd(date_match[0])
        return date_formatted
    else:
        return None


def name_document():
    start_text = START_TEXT
    end_text = END_TEXT
    origin_folder_path = '/Users/shivendrasingh/PycharmProjects/ocrpdf/output/'
    target_folder_path = '/Users/shivendrasingh/PycharmProjects/ocrpdf/output_final/'
    pdf_files = [f for f in listdir(origin_folder_path) if isfile(join(origin_folder_path, f))]

    for pdf in pdf_files:
        with open(origin_folder_path + pdf, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            page = pdf_reader.pages[0]
            page_text = page.extract_text()
            date_str = find_dates(page_text)
            found_split, split_reason = find_start_index(page_text, start_text)

            if not found_split:
                found_split, split_reason = find_end_index(page_text, end_text)

            if not found_split:
                split_reason = "Sonstiges|Anhang"

            new_filename = pdf[0:-4] + "---" + str(date_str) + "-" + "VAMG" + "-" + str(split_reason) + ".pdf"

        shutil.copy(origin_folder_path+pdf, target_folder_path+new_filename)


if __name__ == '__main__':
    if REMOVE_BLANK_PAGES:
        stg_10_remove_blank_pages()

    if CONVERT_SCANNED_DOC_TO_PDF:
        stg_20_generate_ocr_brewed_pdfs()

    if SPLIT_PDF_DOCS:
        stg_30_split_pdf()

    if NAME_SPLITTED_DOCS:
        name_document()

    if CONVERT_PDF_TO_IMAGE:
        convert_pdf_to_images()

    if SPLIT_MACHINE_HANDWRITTEN_TEXTS:
        split_machine_handwritten_pdf()
