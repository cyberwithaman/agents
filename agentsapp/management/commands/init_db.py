import os
import sqlite3
import requests
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings

from agentsapp.models import (
    LLMModel, Tool, AgentType, UserProfile, UserPreference, 
    Conversation, Message, AgentConfig, Database
)


class Command(BaseCommand):
    help = 'Initialize the database with default data'

    def handle(self, *args, **options):
        self.stdout.write('Initializing database...')
        
        # Create default admin user if it doesn't exist
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@example.com',
                password='admin'
            )
            self.stdout.write(self.style.SUCCESS('Created default admin user (username: admin, password: admin)'))
        
        # Create default LLM models
        if not LLMModel.objects.exists():
            LLMModel.objects.create(
                name='llama2',
                provider='ollama',
                api_base='http://localhost:11434/api',
                temperature=0.0,
                max_tokens=512,
                is_active=True
            )
            LLMModel.objects.create(
                name='llama3',
                provider='ollama',
                api_base='http://localhost:11434/api',
                temperature=0.0,
                max_tokens=512,
                is_active=False
            )
            self.stdout.write(self.style.SUCCESS('Created default LLM models'))
        
        # Create default agent types
        if not AgentType.objects.exists():
            AgentType.objects.create(
                name='Music Catalog Agent',
                description='Specialized agent for music catalog queries'
            )
            AgentType.objects.create(
                name='Invoice Agent',
                description='Specialized agent for invoice and purchase queries'
            )
            AgentType.objects.create(
                name='Supervisor Agent',
                description='Supervisor agent that routes queries to specialized agents'
            )
            self.stdout.write(self.style.SUCCESS('Created default agent types'))
        
        # Create default tools
        if not Tool.objects.exists():
            Tool.objects.create(
                name='get_albums_by_artist',
                description='Get albums by an artist',
                function_name='get_albums_by_artist'
            )
            Tool.objects.create(
                name='get_tracks_by_artist',
                description='Get songs by an artist',
                function_name='get_tracks_by_artist'
            )
            Tool.objects.create(
                name='get_songs_by_genre',
                description='Get songs by genre',
                function_name='get_songs_by_genre'
            )
            Tool.objects.create(
                name='check_for_songs',
                description='Check if specific songs exist',
                function_name='check_for_songs'
            )
            Tool.objects.create(
                name='get_invoices_by_customer_sorted_by_date',
                description='Get invoices for a customer sorted by date',
                function_name='get_invoices_by_customer_sorted_by_date'
            )
            Tool.objects.create(
                name='get_invoices_sorted_by_unit_price',
                description='Get invoices sorted by unit price',
                function_name='get_invoices_sorted_by_unit_price'
            )
            Tool.objects.create(
                name='get_employee_by_invoice_and_customer',
                description='Get employee associated with invoice and customer',
                function_name='get_employee_by_invoice_and_customer'
            )
            self.stdout.write(self.style.SUCCESS('Created default tools'))
        
        # Create Chinook database if it doesn't exist
        if not Database.objects.exists():
            # Create data directory if it doesn't exist
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'data')
            os.makedirs(data_dir, exist_ok=True)
            
            # Path to the Chinook database
            db_path = os.path.join(data_dir, 'chinook.db')
            
            # Check if the database already exists
            if not os.path.exists(db_path):
                self.stdout.write('Creating Chinook database...')
                
                # Create a new SQLite database
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Execute SQL to create the schema
                # Note: This is a simplified version of the Chinook schema
                cursor.executescript('''
                    -- Create Artist table
                    CREATE TABLE Artist (
                        ArtistId INTEGER PRIMARY KEY AUTOINCREMENT,
                        Name TEXT
                    );
                    
                    -- Create Album table
                    CREATE TABLE Album (
                        AlbumId INTEGER PRIMARY KEY AUTOINCREMENT,
                        Title TEXT,
                        ArtistId INTEGER,
                        FOREIGN KEY (ArtistId) REFERENCES Artist(ArtistId)
                    );
                    
                    -- Create Genre table
                    CREATE TABLE Genre (
                        GenreId INTEGER PRIMARY KEY AUTOINCREMENT,
                        Name TEXT
                    );
                    
                    -- Create Track table
                    CREATE TABLE Track (
                        TrackId INTEGER PRIMARY KEY AUTOINCREMENT,
                        Name TEXT,
                        AlbumId INTEGER,
                        MediaTypeId INTEGER,
                        GenreId INTEGER,
                        Composer TEXT,
                        Milliseconds INTEGER,
                        Bytes INTEGER,
                        UnitPrice NUMERIC,
                        FOREIGN KEY (AlbumId) REFERENCES Album(AlbumId),
                        FOREIGN KEY (GenreId) REFERENCES Genre(GenreId)
                    );
                    
                    -- Create Customer table
                    CREATE TABLE Customer (
                        CustomerId INTEGER PRIMARY KEY AUTOINCREMENT,
                        FirstName TEXT,
                        LastName TEXT,
                        Company TEXT,
                        Address TEXT,
                        City TEXT,
                        State TEXT,
                        Country TEXT,
                        PostalCode TEXT,
                        Phone TEXT,
                        Fax TEXT,
                        Email TEXT,
                        SupportRepId INTEGER
                    );
                    
                    -- Create Employee table
                    CREATE TABLE Employee (
                        EmployeeId INTEGER PRIMARY KEY AUTOINCREMENT,
                        LastName TEXT,
                        FirstName TEXT,
                        Title TEXT,
                        ReportsTo INTEGER,
                        BirthDate TEXT,
                        HireDate TEXT,
                        Address TEXT,
                        City TEXT,
                        State TEXT,
                        Country TEXT,
                        PostalCode TEXT,
                        Phone TEXT,
                        Fax TEXT,
                        Email TEXT,
                        FOREIGN KEY (ReportsTo) REFERENCES Employee(EmployeeId)
                    );
                    
                    -- Create Invoice table
                    CREATE TABLE Invoice (
                        InvoiceId INTEGER PRIMARY KEY AUTOINCREMENT,
                        CustomerId INTEGER,
                        InvoiceDate TEXT,
                        BillingAddress TEXT,
                        BillingCity TEXT,
                        BillingState TEXT,
                        BillingCountry TEXT,
                        BillingPostalCode TEXT,
                        Total NUMERIC,
                        FOREIGN KEY (CustomerId) REFERENCES Customer(CustomerId)
                    );
                    
                    -- Create InvoiceLine table
                    CREATE TABLE InvoiceLine (
                        InvoiceLineId INTEGER PRIMARY KEY AUTOINCREMENT,
                        InvoiceId INTEGER,
                        TrackId INTEGER,
                        UnitPrice NUMERIC,
                        Quantity INTEGER,
                        FOREIGN KEY (InvoiceId) REFERENCES Invoice(InvoiceId),
                        FOREIGN KEY (TrackId) REFERENCES Track(TrackId)
                    );
                    
                    -- Insert sample data
                    -- Artist
                    INSERT INTO Artist (Name) VALUES ('The Rolling Stones');
                    INSERT INTO Artist (Name) VALUES ('Led Zeppelin');
                    INSERT INTO Artist (Name) VALUES ('Queen');
                    INSERT INTO Artist (Name) VALUES ('Hiphop Tamizha');
                    
                    -- Album
                    INSERT INTO Album (Title, ArtistId) VALUES ('Sticky Fingers', 1);
                    INSERT INTO Album (Title, ArtistId) VALUES ('IV', 2);
                    INSERT INTO Album (Title, ArtistId) VALUES ('A Night at the Opera', 3);
                    INSERT INTO Album (Title, ArtistId) VALUES ('Hip Hop Tamizhan', 4);
                    INSERT INTO Album (Title, ArtistId) VALUES ('Meesaya Murukku', 4);
                    INSERT INTO Album (Title, ArtistId) VALUES ('Naa Oru Alien', 4);
                    
                    -- Genre
                    INSERT INTO Genre (Name) VALUES ('Rock');
                    INSERT INTO Genre (Name) VALUES ('Blues');
                    INSERT INTO Genre (Name) VALUES ('Pop');
                    INSERT INTO Genre (Name) VALUES ('Hip Hop');
                    INSERT INTO Genre (Name) VALUES ('Tamil Hip Hop');
                    
                    -- Track
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Brown Sugar', 1, 1, 1, 'Jagger/Richards', 228000, 4500000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Stairway to Heaven', 2, 1, 1, 'Page/Plant', 482000, 8200000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Bohemian Rhapsody', 3, 1, 1, 'Mercury', 354000, 6700000, 0.99);
                    
                    -- Hiphop Tamizha Tracks - Hip Hop Tamizhan Album
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Manithan Tamizhan', 4, 1, 5, 'Adhi', 252000, 5000000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Tamizhanda', 4, 1, 5, 'Adhi', 189000, 4200000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Tamizh Theriyum', 4, 1, 5, 'Adhi', 192000, 4300000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Club Le Mabbu Le', 4, 1, 5, 'Adhi', 216000, 4800000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Sentamizh Penne', 4, 1, 5, 'Adhi', 200000, 4500000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Iraiva', 4, 1, 5, 'Adhi', 280000, 5500000, 0.99);
                    
                    -- Hiphop Tamizha Tracks - Meesaya Murukku Album (Film Soundtrack)
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Sakkarakatti', 5, 1, 5, 'Adhi', 231000, 5100000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Enna Nadanthalum', 5, 1, 5, 'Adhi', 240000, 5200000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Vaadi Nee Vaa', 5, 1, 5, 'Adhi', 212000, 4700000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Machi Engalukku', 5, 1, 5, 'Adhi', 227000, 5000000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Great Ji', 5, 1, 5, 'Adhi', 213000, 4800000, 0.99);
                    
                    -- Hiphop Tamizha Tracks - Naa Oru Alien Album
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Yaarumey Venam', 6, 1, 5, 'Adhi', 245000, 5200000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Tamizhi', 6, 1, 5, 'Adhi', 253000, 5300000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Naa Oru Alien', 6, 1, 5, 'Adhi', 261000, 5400000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Poi Poi Poi', 6, 1, 5, 'Adhi', 236000, 5100000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Takkaru Takkaru', 6, 1, 5, 'Adhi', 271000, 5600000, 0.99);
                    
                    -- Additional Hiphop Tamizha Singles and Popular Songs
                    INSERT INTO Album (Title, ArtistId) VALUES ('Singles Collection', 4);
                    INSERT INTO Album (Title, ArtistId) VALUES ('Thani Oruvan', 4);
                    INSERT INTO Album (Title, ArtistId) VALUES ('Natpe Thunai', 4);
                    
                    -- Singles
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Vaadi Pulla Vaadi', 7, 1, 5, 'Adhi', 256000, 5300000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Quarantine & Chill', 7, 1, 5, 'Adhi', 220000, 4900000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Oorukaaran', 7, 1, 5, 'Adhi', 235000, 5100000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Chinna Paiyan', 7, 1, 5, 'Adhi', 243000, 5200000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Nadanthavaraikumey', 7, 1, 5, 'Adhi', 250000, 5300000, 0.99);
                    
                    -- Thani Oruvan
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Theemai Dhaan Vellum', 8, 1, 5, 'Adhi', 247000, 5200000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Thani Oruvan Title Track', 8, 1, 5, 'Adhi', 235000, 5100000, 0.99);
                    
                    -- Natpe Thunai
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Kerala Song', 9, 1, 5, 'Adhi', 232000, 5000000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Vengamavan', 9, 1, 5, 'Adhi', 228000, 4900000, 0.99);
                    INSERT INTO Track (Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
                    VALUES ('Veedhikor Jaadhi', 9, 1, 5, 'Adhi', 242000, 5100000, 0.99);
                    
                    -- Employee
                    INSERT INTO Employee (LastName, FirstName, Title, Email)
                    VALUES ('Smith', 'John', 'Sales Support Agent', 'john@example.com');
                    
                    -- Customer
                    INSERT INTO Customer (FirstName, LastName, Phone, Email, SupportRepId)
                    VALUES ('Jane', 'Doe', '+55 (12) 3923-5555', 'jane@example.com', 1);
                    
                    -- Invoice
                    INSERT INTO Invoice (CustomerId, InvoiceDate, Total)
                    VALUES (1, '2025-08-07 00:00:00', 8.91);
                    
                    -- InvoiceLine
                    INSERT INTO InvoiceLine (InvoiceId, TrackId, UnitPrice, Quantity)
                    VALUES (1, 1, 0.99, 3);
                    INSERT INTO InvoiceLine (InvoiceId, TrackId, UnitPrice, Quantity)
                    VALUES (1, 2, 0.99, 3);
                    INSERT INTO InvoiceLine (InvoiceId, TrackId, UnitPrice, Quantity)
                    VALUES (1, 3, 0.99, 3);
                ''')
                
                conn.commit()
                conn.close()
                
                self.stdout.write(self.style.SUCCESS('Created Chinook database'))
            
            # Register the database in Django
            Database.objects.create(
                name='Chinook',
                description='Sample music store database',
                connection_string=f'sqlite:///{db_path}',
                is_active=True
            )
            self.stdout.write(self.style.SUCCESS('Registered Chinook database'))
        
        # Create default agent configuration
        if not AgentConfig.objects.exists():
            AgentConfig.objects.create(
                name='Default Configuration',
                description='Default agent configuration',
                config_json='{"max_steps": 10, "temperature": 0.0}',
                is_active=True
            )
            self.stdout.write(self.style.SUCCESS('Created default agent configuration'))
        
        self.stdout.write(self.style.SUCCESS('Database initialization complete!')) 