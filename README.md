# regis-marie-lms

erDiagram
    USERS ||--o{ CLASSES : "creates (teacher_id)"
    USERS ||--o{ GROUPS : "creates (teacher_id)"
    USERS ||--o{ CLASS_MEMBERSHIPS : "enrolls (user_id)"
    USERS ||--o{ GROUP_MEMBERSHIPS : "joins (user_id)"
    USERS ||--o{ SUBMISSIONS : "submits (user_id)"
    USERS ||--o{ NOTIFICATIONS : "receives (user_id)"
    USERS ||--o{ ACTIVITIES : "assigns (teacher_id)"

    CLASSES ||--o{ CLASS_MEMBERSHIPS : "contains (class_id)"
    CLASSES ||--o{ LESSONS : "holds (class_id)"
    CLASSES ||--o{ ACTIVITIES : "contains (class_id)"

    GROUPS ||--o{ GROUP_MEMBERSHIPS : "contains (group_id)"

    ACTIVITIES ||--o{ SUBMISSIONS : "receives (activity_id)"
    ACTIVITIES ||--o{ NOTIFICATIONS : "triggers (activity_id)"

    SUBMISSIONS ||--o{ NOTIFICATIONS : "triggers (submission_id)"

    USERS {
        bigint id PK
        text email UK
        text password
        text full_name
        text role
        text student_id
        text course
        text year_level
        text section
        text position
        timestamptz created_at
    }

    CLASSES {
        bigint id PK
        text code UK
        text subject
        text course
        text year_level
        text section
        bigint teacher_id FK
        text status
        timestamptz created_at
    }

    CLASS_MEMBERSHIPS {
        bigint id PK
        bigint class_id FK
        bigint user_id FK
        timestamptz joined_at
    }

    GROUPS {
        bigint id PK
        text code UK
        text name
        text course
        text year_level
        text section
        bigint teacher_id FK
        text status
        timestamptz created_at
    }

    GROUP_MEMBERSHIPS {
        bigint id PK
        bigint group_id FK
        bigint user_id FK
        timestamptz joined_at
    }

    LESSONS {
        bigint id PK
        bigint class_id FK
        text title
        text content
        text file_url
        text link_url
        timestamptz created_at
    }

    ACTIVITIES {
        bigint id PK
        bigint class_id FK
        bigint teacher_id FK
        text title
        text description
        int total_points
        timestamptz due_date
        timestamptz deadline
        text file_url
        text link_url
        timestamptz created_at
    }

    SUBMISSIONS {
        bigint id PK
        bigint activity_id FK
        bigint user_id FK
        text comments
        text link_url
        text file_url
        text status
        numeric score
        numeric grade
        timestamptz submitted_at
        timestamptz created_at
    }

    NOTIFICATIONS {
        bigint id PK
        bigint user_id FK
        text title
        text message
        text type
        text link
        boolean is_read
        bigint activity_id FK
        bigint submission_id FK
        timestamptz created_at
    }
