import argparse
import os
import logging
import sys

from datetime import datetime
from glob import glob
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.DEBUG)

class Migrate:
    def __init__(self, command, database_url, migration_name=None):
        self.command = command
        self.base_folder = 'migrations'
        self.files = [file.split("/")[-1] for file in glob(f"./{self.base_folder}/*")]
        self.files.sort()
        self.sql_engine=create_engine(database_url)
        self.migration_name = migration_name

        self.init_migration_table()
        
        if self.command == 'execute':
            self.execute_migrations()
        
        if self.command == 'rollback':
            if migration_name == None:
                logging.error('missing rollback arg')
                return
            
            self.rollback_migration()
        
        if self.command == 'create':
            self.create_migration()

    def init_migration_table(self):
        logging.info("EXECUTING MIGRATION INITIALIZER")
        with self.sql_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id serial NOT NULL,
                    "name" varchar NOT NULL,
                    app varchar NOT NULL,
                    applied_at timestamptz(0) NOT NULL DEFAULT now(),
                    CONSTRAINT migrations_pk PRIMARY KEY (id)
                )
            """))
        logging.info("MIGRATION INITIALIZED SUCCESSFULLY")

    def create_migration(self):
        if not os.path.exists(self.base_folder):
            os.makedirs(self.base_folder)

        file_name = f'{self.base_folder}/{datetime.now().strftime("%Y%m%d%H%M%S")}_{self.migration_name}.sql'
        with open(file_name, "w") as f:
            f.write("""-- Paste your migrations here to apply inside database\n\n=====DOWN\n\n-- Paste your rollback queries to rollback database modifications""")

    def execute_migrations(self):
        logging.info("INITIALIZING MIGRATIONS EXECUTION\n")
        with self.sql_engine.connect() as conn:
            migrated = conn.execute(text("""
                SELECT name FROM migrations
            """))

        migrated = [item[0] for item in migrated.fetchall()]
        to_migrate = [item for item in self.files if item not in migrated]

        if len(to_migrate) == 0:
            logging.info("NO MIGRATIONS TO BE EXECUTED\nYOU SHOULD ENTER COMMAND: migration create 'migration_name' ")
            exit(0)

        with self.sql_engine.connect() as conn:
            for file in to_migrate:
                with open(f"{self.base_folder}/{file}", "r") as f:
                    archive = f.read()
                    up = archive
                    if "=====DOWN" in archive:
                        split = archive.split("=====DOWN")
                        up = split[0]

                    logging.info(f"APPLYING -> {f.name}")
                    conn.execute(up)
                    conn.execute(text("""
                        INSERT INTO public.migrations
                        (name, app)
                        VALUES (:name, :app)
                    """),
                        name=file,
                        app="app"
                    )

            logging.info("\nALL MIGRATIONS APPLIED SUCCESSFULLY")

    def rollback_migration(self):
        logging.info(f"PREPARING TO ROLLBACK MIGRATION {self.migration_name}")
        with self.sql_engine.connect() as conn, open(f"{self.base_folder}/{self.migration_name}.sql", "r") as f:
            archive = f.read()
            down = archive
            if "=====DOWN" in archive:
                split = archive.split("=====DOWN")
                down = split[1]

            logging.info(f"ROLLING BACK -> {f.name}")
            conn.execute(down)
            conn.execute(text("""
                INSERT INTO public.migrations
                (name, app)
                VALUES (:name, :app)
            """),
                name=f"{self.migration_name}.sql",
                app="app_rollback"
            )
        logging.info("ROLLBACK EXECUTED SUCCESSFULLY")
        exit(0)


def main():
    parser = argparse.ArgumentParser(description='Migrate and rollback database scripts')
    parser.add_argument('command', help="command to execute inside dbms")
    parser.add_argument('--driver', help="SQL Driver to use")
    parser.add_argument('--dbstring', help="Add dbstring to connection if you didn't set DATABASE_URL environment var")
    parser.add_argument('--migration_name', help="Inform migration name to create or rollback sql migation file")
    
    args = parser.parse_args()

    load_dotenv()

    if not args.dbstring and 'DATABASE_URL' not in os.environ:
        logging.error('dbstring is missing, you have to provide it as DATABASE_URL environment variable, or via --dbstring positional argument of command')
        return

    Migrate(
        command=args.command,
        database_url=f"postgresql+psycopg2://{os.getenv('DATABASE_URL') if 'DATABASE_URL' in os.environ else args.dbstring}",
        migration_name=args.migration_name
    )
