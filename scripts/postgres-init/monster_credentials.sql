--
-- PostgreSQL database dump
--

-- Dumped from database version 14.13 (Homebrew)
-- Dumped by pg_dump version 14.13 (Homebrew)

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
-- Name: monster_credentials; Type: DATABASE; Schema: -; Owner: -
--

CREATE DATABASE monster_credentials WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE = 'C';


\connect monster_credentials

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
-- Name: credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credentials (
    id character varying NOT NULL,
    name character varying NOT NULL,
    user_id character varying,
    tenant_id character varying NOT NULL,
    tool_factory_id character varying NOT NULL,
    scope character varying NOT NULL,
    secrets_json character varying
);


--
-- Name: credentialsecret; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credentialsecret (
    id integer NOT NULL,
    tenant_id character varying NOT NULL,
    user_id character varying,
    credential_id character varying NOT NULL,
    secret bytea NOT NULL
);


--
-- Name: credentialsecret_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.credentialsecret_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: credentialsecret_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.credentialsecret_id_seq OWNED BY public.credentialsecret.id;

--
-- Name: credentialsecret id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credentialsecret ALTER COLUMN id SET DEFAULT nextval('public.credentialsecret_id_seq'::regclass);


--
-- Name: credentials credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_pkey PRIMARY KEY (id);


--
-- Name: credentialsecret credentialsecret_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credentialsecret
    ADD CONSTRAINT credentialsecret_pkey PRIMARY KEY (id);



--
-- PostgreSQL database dump complete
--

