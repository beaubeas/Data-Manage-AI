--
-- PostgreSQL database dump
--

-- Dumped from database version 14.10 (Homebrew)
-- Dumped by pg_dump version 14.10 (Homebrew)

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

SET default_tablespace = '';

SET default_table_access_method = heap;



--
-- Name: alembic_version; Type: TABLE; Schema: public
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);

--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public
--

COPY public.alembic_version (version_num) FROM stdin;
722cd8129182
\.


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- PostgreSQL database dump complete
--



--
-- Name: agents; Type: TABLE; Schema: public
--

CREATE TABLE public.agents (
    id character varying NOT NULL,
    name character varying NOT NULL,
    user_id character varying,
    tenant_id character varying,
    description character varying,
    system_prompt character varying,
    model character varying,
    input_mode character varying NOT NULL,
    trigger character varying NOT NULL,
    welcome_message character varying,
    tools character varying,
    trigger_arg character varying
);

--
-- Name: credentials; Type: TABLE; Schema: public
--

CREATE TABLE public.credentials (
    id character varying NOT NULL,
    name character varying NOT NULL,
    user_id character varying,
    tenant_id character varying NOT NULL,
    scope character varying NOT NULL,
    tool_factory_id character varying NOT NULL,
    secrets_json character varying
);

--
-- Name: credentialsecret; Type: TABLE; Schema: public
--

CREATE TABLE public.credentialsecret (
    id integer NOT NULL,
    tenant_id character varying NOT NULL,
    user_id character varying,
    credential_id character varying NOT NULL,
    secret bytea NOT NULL
);

--
-- Name: credentialsecret_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.credentialsecret_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: credentialsecret_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.credentialsecret_id_seq OWNED BY public.credentialsecret.id;


--
-- Name: run; Type: TABLE; Schema: public
--

CREATE TABLE public.run (
    tenant_id character varying NOT NULL,
    user_id character varying NOT NULL,
    id uuid NOT NULL,
    input character varying,
    input_mode character varying NOT NULL,
    turn_limit integer NOT NULL,
    timeout integer NOT NULL,
    result_channel character varying,
    logs_channel character varying,
    status character varying NOT NULL,
    chatengine_id uuid,
    created_at timestamp without time zone NOT NULL,
    last_interaction timestamp without time zone NOT NULL,
    agent_id character varying NOT NULL
);

CREATE TABLE public.emailmsgsprocessed (
    uid character varying NOT NULL,
    from_field character varying NOT NULL,
    to_field character varying NOT NULL,
    subject_field character varying NOT NULL,
    processed integer,
    PRIMARY KEY (uid)
);

--
-- Name: credentialsecret id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.credentialsecret ALTER COLUMN id SET DEFAULT nextval('public.credentialsecret_id_seq'::regclass);


--
-- Name: agents agents_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT agents_pkey PRIMARY KEY (id);



--
-- Name: credentials credentials_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_pkey PRIMARY KEY (id);


--
-- Name: credentialsecret credentialsecret_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.credentialsecret
    ADD CONSTRAINT credentialsecret_pkey PRIMARY KEY (id);


--
-- Name: run run_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.run
    ADD CONSTRAINT run_pkey PRIMARY KEY (id);


--
-- Name: run run_agent_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.run
    ADD CONSTRAINT run_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id);


--
-- PostgreSQL database dump complete
--

