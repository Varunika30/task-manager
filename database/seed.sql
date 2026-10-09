-- Sample tasks for the demo user (id 1, created by app.py: demo@example.com / demo1234).
-- Dates are relative to "now" so the demo always looks fresh.

INSERT INTO tasks (user_id, title, description, category, priority, due_datetime, reminder_interval_minutes) VALUES
(1, 'Finish assignment draft', 'Write the introduction and outline the main sections.', 'Study',    'High',   strftime('%Y-%m-%dT%H:%M','now','localtime','+3 hours'), 60),
(1, '30-minute workout',       'Warm up, main set, stretch.',                              'Health',   'Medium', strftime('%Y-%m-%dT%H:%M','now','localtime','+5 hours'), 120),
(1, 'Tidy the desk',           'Clear the clutter and organise notes.',                    'Home',     'Low',    strftime('%Y-%m-%dT%H:%M','now','localtime','+1 hours'), 30),
(1, 'Read 20 pages',           'Pick up where you left off.',                              'Study',    'Medium', strftime('%Y-%m-%dT%H:%M','now','localtime','+1 days'),  0),
(1, 'Plan next week',          'List the top three goals for the week.',                   'Planning', 'Medium', strftime('%Y-%m-%dT%H:%M','now','localtime','+3 days'),  0),
(1, 'Reply to pending emails', 'Clear the inbox backlog.',                                 'Work',     'High',   strftime('%Y-%m-%dT%H:%M','now','localtime','-2 hours'), 60);
