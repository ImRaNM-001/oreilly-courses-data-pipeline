"""
Apache Airflow introduced the TaskFlow API which allows to create tasks using Python decorators like @task. 
This is a cleaner and more intuitive way of writing tasks without needing to manually use operators like PythonOperator.
"""
# dag - directed acyclic graph

# tasks: 
    # 1) fetch articles from medium.com site (extract) 
    # 2) clean data (transform) 
    # 3) create and store data in table on postgres (load)

# hooks - allows connection to postgres
# dependencies

import logging
import json
import urllib.parse
from datetime import timedelta
from pathlib import Path
from yaml import safe_load, YAMLError
from playwright.sync_api import sync_playwright
from airflow.decorators import dag, task
from airflow.utils.dates import days_ago
from airflow.providers.postgres.hooks.postgres import PostgresHook

root_path: Path = Path(__file__).parent.parent
def load_config(config_path: Path) -> dict[str, object]:
    """
    Load configuratons from an YAML file
    """
    try:
        with open(config_path, 'r') as file:
            config = safe_load(file)
        logging.info(f"Config loaded from {config_path}")
        return config
    
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found at {config_path}")
    
    except YAMLError:
        raise YAMLError("Error parsing the config file")
    
config = load_config(root_path / 'config/config.yaml')

# Define the default arguments for the DAG
"""
    'start_date': days_ago(1) --> This function is used to set the start_date to one day ago from the current date and time, a convenient way to specify a relative start date when the DAG is expected to start running from a point in the past relative to the current date. This is particularly useful for testing or when we want to ensure that the DAG runs immediately after being deployed.
"""
default_args = {
    'owner': 'airflow',
    'start_date': days_ago(1),          
    'depends_on_past': False,        
    'retries': 1,
    'retry_delay': timedelta(minutes = 5),
}

# Define the DAG using the @dag decorator
"""
    @dag decorator: Marks a function as a DAG. DAG configuration is passed as arguments to the decorator.
    @task decorator:  Transforms a regular Python function into an Airflow task.
    Intuitive Task Dependencies: Dependencies are implied by passing the output of one task to another as function arguments
"""

@dag(dag_id = 'fetch_oreilly_courses_data',
    default_args = default_args,
    description = 'A DAG to fetch MLOps courses data from Oreilly.com site, clean the data, and store it in a PostgreSQL database',
    schedule_interval = timedelta(days = 1),
    catchup = False
)
# Define a DAG in a pythonic function
def fetch_oreilly_courses_data():
    # Define the tasks:
    # Task 1: Query the Medium website to fetch MLOps articles (extract)
    @task
    def fetch_course_data(page_element):
        query_params = config['query_params']
        base_url = config['base_url']
        course_info_list = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless = True)
            page = browser.new_page()
                   
            # Construct the URL with query parameters
            query_params_string = urllib.parse.urlencode(query_params, doseq = True)
            url = f'{base_url}?{query_params_string}'
            page.goto(url)
            
            # Wait for the page to load completely
            page.wait_for_load_state('networkidle')
            
            # Get all link elements and their corresponding text
            links = page.query_selector_all(page_element) 

            for each_link in links:                  
                course_info_list.append(each_link.inner_text())                        
            
            browser.close()
        return course_info_list                     

    # Task 2: Transform the data and create a table on postgres (transform)
    @task
    def clean_course_data(title_list, authors_list, publisher_list, published_date_list) -> list[dict[str, object]]:
        # Remove the '\xa0' character and replace 'By' with 'By '
        authors_list = [author.replace('\xa0', '')
                        .replace('By', 'By ') 
                        for author in authors_list]
        
        # Maintain identical length of the list
        max_length = max(len(title_list), 
                         len(authors_list), 
                         len(publisher_list), 
                         len(published_date_list))
        
        title_list.extend([None] * (max_length - len(title_list)))
        authors_list.extend([None] * (max_length - len(authors_list)))
        publisher_list.extend([None] * (max_length - len(publisher_list)))
        published_date_list.extend([None] * (max_length - len(published_date_list)))

        # Create a list of dictionaries with the extracted data (which is a list)
        courses_data_list: list[dict[str, object]] = [{                        
            'Course Title': title_list[_],
            'Author': authors_list[_],
            'Publisher': publisher_list[_],
            'Published Date': published_date_list[_]
        }
        for _ in range(max_length)
    ]

        # Check if the "list of dictonaries" result is JSON serializable - to refrain Airflow throwing "<coroutine object" error
        try:
            json.dumps(courses_data_list)
            logging.info('clean_course_data() function returns a JSON serializable object')

        except TypeError as error:
            raise TypeError(f'clean_course_data() returned a non-serializable object: {error}')
        return courses_data_list                                    # Type of "courses_data_list" is: <class 'list'>

    # Task 3: Insert data in table on postgres db (load)
    @task
    def insert_courses_data_to_db(courses_data_list):
        if not courses_data_list:
            raise ValueError('No course information fetched from the website')
        
        # Check: Ensure that courses_data_list is a "list of dictionaries"
        if not isinstance(courses_data_list, list):
            raise ValueError('courses_data_list: Expected a list of dictionaries')
        
        for course in courses_data_list:
            if not isinstance(course, dict):
                logging.info(f'Type of each course is: {type(course)}')
                raise ValueError('Inside courses_data_list > each course should be a dictionary')

        postgres_hook = PostgresHook(postgres_conn_id = 'oreilly_courses_connection')
        
        try:
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS courses(
                course_id SERIAL PRIMARY KEY,
                course_title VARCHAR(255) NOT NULL,
                authors VARCHAR(255),
                publisher VARCHAR(255),
                published_date VARCHAR(255)
            );
            """
            postgres_hook.run(create_table_sql)
            logging.info('Courses table created successfully')
        
        except Exception as exception:
            logging.error(f'Error creating table into PostgreSQL: {exception}')
            raise

        # Prepare the data for bulk insertion
        table_data_to_insert = [
            (course['Course Title'], 
                course['Author'], 
                course['Publisher'], 
                course['Published Date']) for course in courses_data_list]
        
        try:
            # Insert multiple rows at once to the table
            postgres_hook.insert_rows(table = 'courses', 
                                      rows = table_data_to_insert, 
                                      target_fields = ['course_title', 'authors', 'publisher', 'published_date'])
            logging.info('Course Data inserted successfully to PostgreSQL db')

        except Exception as exception:
            logging.error(f'Error inserting data into PostgreSQL: {exception}')
            raise

    # Set task dependencies
    title_list = fetch_course_data(config['page_element_selector'][0])
    authors_list = fetch_course_data(config['page_element_selector'][1])
    publisher_list = fetch_course_data(config['page_element_selector'][2])
    published_date_list = fetch_course_data(config['page_element_selector'][3])

    courses_data_list = clean_course_data(title_list, authors_list, publisher_list, published_date_list)
    insert_courses_data_to_db(courses_data_list)

# Instantiate the DAG
dag = fetch_oreilly_courses_data()
