--
-- PostgreSQL database dump
--

\restrict szgV47m5sw48s8p59pT21Rhqykd1Py2MvIRsfZPY3Q881wMYJxG8urupwZc1EgN

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 16.11 (Debian 16.11-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: csvimportstatus; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.csvimportstatus AS ENUM (
    'pending',
    'processing',
    'ready',
    'committed',
    'failed'
);


ALTER TYPE public.csvimportstatus OWNER TO postgres;

--
-- Name: magiclinkpurpose; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.magiclinkpurpose AS ENUM (
    'email_confirm',
    'check_in',
    'signup_confirm',
    'signup_manage'
);


ALTER TYPE public.magiclinkpurpose OWNER TO postgres;

--
-- Name: notificationtype; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.notificationtype AS ENUM (
    'email',
    'sms'
);


ALTER TYPE public.notificationtype OWNER TO postgres;

--
-- Name: privacymode; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.privacymode AS ENUM (
    'full',
    'initials',
    'anonymous'
);


ALTER TYPE public.privacymode OWNER TO postgres;

--
-- Name: quarter; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.quarter AS ENUM (
    'winter',
    'spring',
    'summer',
    'fall'
);


ALTER TYPE public.quarter OWNER TO postgres;

--
-- Name: signupstatus; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.signupstatus AS ENUM (
    'confirmed',
    'waitlisted',
    'cancelled',
    'pending',
    'checked_in',
    'attended',
    'no_show'
);


ALTER TYPE public.signupstatus OWNER TO postgres;

--
-- Name: slottype; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.slottype AS ENUM (
    'orientation',
    'period'
);


ALTER TYPE public.slottype OWNER TO postgres;

--
-- Name: userrole; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.userrole AS ENUM (
    'admin',
    'organizer',
    'participant'
);


ALTER TYPE public.userrole OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alembic_version (
    version_num character varying(128) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO postgres;

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.audit_logs (
    id uuid NOT NULL,
    actor_id uuid,
    action character varying(128) NOT NULL,
    entity_type character varying(128) NOT NULL,
    entity_id character varying(128),
    extra json,
    "timestamp" timestamp with time zone
);


ALTER TABLE public.audit_logs OWNER TO postgres;

--
-- Name: csv_imports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.csv_imports (
    id uuid NOT NULL,
    uploaded_by uuid NOT NULL,
    filename character varying(512) NOT NULL,
    raw_csv_hash character varying(64) NOT NULL,
    status public.csvimportstatus DEFAULT 'pending'::public.csvimportstatus NOT NULL,
    result_payload jsonb,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.csv_imports OWNER TO postgres;

--
-- Name: custom_answers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.custom_answers (
    id uuid NOT NULL,
    signup_id uuid NOT NULL,
    question_id uuid NOT NULL,
    value text NOT NULL
);


ALTER TABLE public.custom_answers OWNER TO postgres;

--
-- Name: custom_questions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.custom_questions (
    id uuid NOT NULL,
    event_id uuid NOT NULL,
    prompt text NOT NULL,
    field_type character varying(32) NOT NULL,
    required boolean,
    options json,
    sort_order integer
);


ALTER TABLE public.custom_questions OWNER TO postgres;

--
-- Name: events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.events (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    location character varying(255),
    visibility character varying(32),
    branding_id character varying(64),
    start_date timestamp with time zone NOT NULL,
    end_date timestamp with time zone NOT NULL,
    max_signups_per_user integer,
    signup_open_at timestamp with time zone,
    signup_close_at timestamp with time zone,
    created_at timestamp with time zone,
    venue_code character varying(4),
    module_slug character varying,
    reminder_1h_enabled boolean DEFAULT true NOT NULL,
    quarter public.quarter,
    year integer,
    week_number integer,
    school character varying(255)
);


ALTER TABLE public.events OWNER TO postgres;

--
-- Name: magic_link_tokens; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.magic_link_tokens (
    id uuid NOT NULL,
    token_hash text NOT NULL,
    signup_id uuid NOT NULL,
    email text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    purpose public.magiclinkpurpose DEFAULT 'email_confirm'::public.magiclinkpurpose NOT NULL,
    volunteer_id uuid
);


ALTER TABLE public.magic_link_tokens OWNER TO postgres;

--
-- Name: module_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.module_templates (
    slug character varying NOT NULL,
    name character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    default_capacity integer DEFAULT 20 NOT NULL,
    duration_minutes integer DEFAULT 90 NOT NULL,
    materials character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    description text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    deleted_at timestamp with time zone
);


ALTER TABLE public.module_templates OWNER TO postgres;

--
-- Name: notifications; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.notifications (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    type public.notificationtype NOT NULL,
    subject character varying(255),
    body text NOT NULL,
    delivery_method character varying(32) NOT NULL,
    delivered_at timestamp with time zone,
    created_at timestamp with time zone
);


ALTER TABLE public.notifications OWNER TO postgres;

--
-- Name: portal_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.portal_events (
    id uuid NOT NULL,
    portal_id uuid NOT NULL,
    event_id uuid NOT NULL
);


ALTER TABLE public.portal_events OWNER TO postgres;

--
-- Name: portals; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.portals (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    description text,
    visibility character varying(32),
    created_at timestamp with time zone
);


ALTER TABLE public.portals OWNER TO postgres;

--
-- Name: refresh_tokens; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.refresh_tokens (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(512) NOT NULL,
    created_at timestamp with time zone,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone
);


ALTER TABLE public.refresh_tokens OWNER TO postgres;

--
-- Name: sent_notifications; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sent_notifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    signup_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    sent_at timestamp with time zone DEFAULT now() NOT NULL,
    provider_id character varying(255)
);


ALTER TABLE public.sent_notifications OWNER TO postgres;

--
-- Name: signups; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.signups (
    id uuid NOT NULL,
    slot_id uuid NOT NULL,
    status public.signupstatus NOT NULL,
    "timestamp" timestamp with time zone,
    reminder_sent boolean DEFAULT false NOT NULL,
    checked_in_at timestamp with time zone,
    reminder_24h_sent_at timestamp with time zone,
    reminder_1h_sent_at timestamp with time zone,
    volunteer_id uuid NOT NULL
);


ALTER TABLE public.signups OWNER TO postgres;

--
-- Name: site_settings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.site_settings (
    id integer NOT NULL,
    default_privacy_mode public.privacymode,
    allowed_email_domain character varying(255)
);


ALTER TABLE public.site_settings OWNER TO postgres;

--
-- Name: site_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.site_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.site_settings_id_seq OWNER TO postgres;

--
-- Name: site_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.site_settings_id_seq OWNED BY public.site_settings.id;


--
-- Name: slots; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.slots (
    id uuid NOT NULL,
    event_id uuid NOT NULL,
    start_time timestamp with time zone NOT NULL,
    end_time timestamp with time zone NOT NULL,
    capacity integer NOT NULL,
    current_count integer NOT NULL,
    slot_type public.slottype DEFAULT 'period'::public.slottype NOT NULL,
    date date DEFAULT CURRENT_DATE NOT NULL,
    location character varying(255)
);


ALTER TABLE public.slots OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    role public.userrole NOT NULL,
    university_id character varying(64),
    notify_email boolean,
    created_at timestamp with time zone,
    deleted_at timestamp with time zone
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: volunteers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.volunteers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email character varying(255) NOT NULL,
    first_name character varying(100) NOT NULL,
    last_name character varying(100) NOT NULL,
    phone_e164 character varying(20),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.volunteers OWNER TO postgres;

--
-- Name: site_settings id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.site_settings ALTER COLUMN id SET DEFAULT nextval('public.site_settings_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: csv_imports csv_imports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.csv_imports
    ADD CONSTRAINT csv_imports_pkey PRIMARY KEY (id);


--
-- Name: custom_answers custom_answers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.custom_answers
    ADD CONSTRAINT custom_answers_pkey PRIMARY KEY (id);


--
-- Name: custom_questions custom_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.custom_questions
    ADD CONSTRAINT custom_questions_pkey PRIMARY KEY (id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: magic_link_tokens magic_link_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.magic_link_tokens
    ADD CONSTRAINT magic_link_tokens_pkey PRIMARY KEY (id);


--
-- Name: magic_link_tokens magic_link_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.magic_link_tokens
    ADD CONSTRAINT magic_link_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: module_templates module_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.module_templates
    ADD CONSTRAINT module_templates_pkey PRIMARY KEY (slug);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: portal_events portal_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.portal_events
    ADD CONSTRAINT portal_events_pkey PRIMARY KEY (id);


--
-- Name: portals portals_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.portals
    ADD CONSTRAINT portals_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_token_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_token_key UNIQUE (token_hash);


--
-- Name: sent_notifications sent_notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sent_notifications
    ADD CONSTRAINT sent_notifications_pkey PRIMARY KEY (id);


--
-- Name: signups signups_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.signups
    ADD CONSTRAINT signups_pkey PRIMARY KEY (id);


--
-- Name: site_settings site_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.site_settings
    ADD CONSTRAINT site_settings_pkey PRIMARY KEY (id);


--
-- Name: slots slots_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.slots
    ADD CONSTRAINT slots_pkey PRIMARY KEY (id);


--
-- Name: portal_events uq_portal_events_portal_id_event_id; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.portal_events
    ADD CONSTRAINT uq_portal_events_portal_id_event_id UNIQUE (portal_id, event_id);


--
-- Name: signups uq_signups_volunteer_id_slot_id; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.signups
    ADD CONSTRAINT uq_signups_volunteer_id_slot_id UNIQUE (volunteer_id, slot_id);


--
-- Name: volunteers uq_volunteers_email; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.volunteers
    ADD CONSTRAINT uq_volunteers_email UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: volunteers volunteers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.volunteers
    ADD CONSTRAINT volunteers_pkey PRIMARY KEY (id);


--
-- Name: ix_magic_link_tokens_email_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_magic_link_tokens_email_created_at ON public.magic_link_tokens USING btree (email, created_at DESC);


--
-- Name: ix_portals_slug; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_portals_slug ON public.portals USING btree (slug);


--
-- Name: ix_slots_start_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_slots_start_time ON public.slots USING btree (start_time);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_volunteers_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_volunteers_email ON public.volunteers USING btree (email);


--
-- Name: uq_sent_notifications_signup_kind; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX uq_sent_notifications_signup_kind ON public.sent_notifications USING btree (signup_id, kind);


--
-- Name: audit_logs audit_logs_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: csv_imports csv_imports_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.csv_imports
    ADD CONSTRAINT csv_imports_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.users(id);


--
-- Name: custom_answers custom_answers_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.custom_answers
    ADD CONSTRAINT custom_answers_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.custom_questions(id);


--
-- Name: custom_answers custom_answers_signup_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.custom_answers
    ADD CONSTRAINT custom_answers_signup_id_fkey FOREIGN KEY (signup_id) REFERENCES public.signups(id);


--
-- Name: custom_questions custom_questions_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.custom_questions
    ADD CONSTRAINT custom_questions_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id);


--
-- Name: events events_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id);


--
-- Name: magic_link_tokens fk_magic_link_tokens_volunteer_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.magic_link_tokens
    ADD CONSTRAINT fk_magic_link_tokens_volunteer_id FOREIGN KEY (volunteer_id) REFERENCES public.volunteers(id) ON DELETE CASCADE;


--
-- Name: signups fk_signups_volunteer_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.signups
    ADD CONSTRAINT fk_signups_volunteer_id FOREIGN KEY (volunteer_id) REFERENCES public.volunteers(id) ON DELETE RESTRICT;


--
-- Name: magic_link_tokens magic_link_tokens_signup_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.magic_link_tokens
    ADD CONSTRAINT magic_link_tokens_signup_id_fkey FOREIGN KEY (signup_id) REFERENCES public.signups(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: portal_events portal_events_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.portal_events
    ADD CONSTRAINT portal_events_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id);


--
-- Name: portal_events portal_events_portal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.portal_events
    ADD CONSTRAINT portal_events_portal_id_fkey FOREIGN KEY (portal_id) REFERENCES public.portals(id);


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: sent_notifications sent_notifications_signup_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sent_notifications
    ADD CONSTRAINT sent_notifications_signup_id_fkey FOREIGN KEY (signup_id) REFERENCES public.signups(id);


--
-- Name: signups signups_slot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.signups
    ADD CONSTRAINT signups_slot_id_fkey FOREIGN KEY (slot_id) REFERENCES public.slots(id);


--
-- Name: slots slots_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.slots
    ADD CONSTRAINT slots_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id);


--
-- PostgreSQL database dump complete
--

\unrestrict szgV47m5sw48s8p59pT21Rhqykd1Py2MvIRsfZPY3Q881wMYJxG8urupwZc1EgN

