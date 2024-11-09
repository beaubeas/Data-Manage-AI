import asyncio
from sqlalchemy import Engine
from sqlmodel   import SQLModel, Session, Field, select
from uuid       import UUID, uuid4
from typing     import Optional, Coroutine, Tuple
from datetime   import datetime, timedelta


import requests
import sys
import time
import pytz
import json


from supercog.shared.services import config, db_connect
from supercog.shared.models   import RunCreate
from supercog.shared.services import config, serve, db_connect

from supercog.engine.db       import Agent

from supercog.shared.models   import CredentialBase
from supercog.shared.logging  import logger
from supercog.shared.services import get_service_host

from supercog.engine.db       import session_context
from supercog.shared.services import config, db_connect
from sqlmodel                import Session
from supercog.engine.db       import session_context
from supercog.engine.triggerable import Triggerable
from supercog.shared.logging import logger

from pytz import utc

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy  import SQLAlchemyJobStore
from apscheduler.executors.pool        import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.schedulers.asyncio    import AsyncIOScheduler
from fastapi import FastAPI
from supercog.engine.db import lifespan_manager

from openai    import OpenAI
from croniter  import croniter
from functools import wraps







#
# GLOBALS:
#
scheduler = None
job_defaults = {
    'coalesce': False,
    'max_instances': 3
}
# Global dictionary to store DailyLimitJobWrapper instances
job_wrappers = {}










#
#FIXME: This all should be rewritten to get rid of the global scheduler and put this all under a class
#



######################################################################################################
# Externally facing GLOBAL functions
#
def job_to_dict(job):
    """ Convert a job object to a dictionary which is serializable. """
    wrapper =   job_wrappers.get(job.name)
    run_count = wrapper.get_run_count() if wrapper else 0
    max_runs =  wrapper.max_runs_per_day if wrapper else 'N/A'
    
    return {
        'id': job.id,
        'name': job.name,
        'next_run_time': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else None,
        'func_ref': f"{job.func_ref}",
        'run_count': run_count,
        'max_runs_per_day': max_runs
    }
       
def internal_get_jobs():
    """ return a list of all the running jobs """
    global scheduler
    if scheduler is not None:
        try:
            jobs = scheduler.get_jobs()
            return [job_to_dict(job) for job in jobs]
        except Exception as e:
            error_str = f"Error getting running jobs: {e}"
            logger.error(error_str)
            return error_str
    return []  # "No jobs currently scheduled"

def internal_cancel_job(job_id):
    """Terminate the job identified by job_id."""
    global scheduler, job_wrappers
    if scheduler is not None:
        try:
            job = scheduler.get_job(job_id)
            if job:
                job_wrappers.pop(job.name, None)  # Remove the wrapper from our dictionary
                scheduler.remove_job(job_id)
                logger.debug(f"Successfully canceled job: {job_id}")
            else:
                logger.warn(f"Job {job_id} not found")
        except Exception as e:
            logger.error(f"Error canceling job {job_id}: {e}")
            

######################################################################################################
# Scheduler related GLOBAL functions
#
def scheduler_start(default_timezone: str = 'America/New_York'):
    global scheduler
    try:
        tz = pytz.timezone(default_timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warn(f"Unknown time zone: {default_timezone}. Falling back to UTC.")
        tz = pytz.UTC

    scheduler = AsyncIOScheduler(
        job_defaults=job_defaults,
        timezone=tz
    )
    logger.info(f"Starting AP Scheduler with default timezone: {tz}")
    scheduler.start()

def is_valid_cron_frequency(cron: dict) -> bool:
    """
    Check if the given cron expression runs at most once per minute.
    
    Args:
        cron (dict): A dictionary representing a cron expression.
        
    Returns:
        bool: True if the cron runs at most once per minute, False otherwise.
    """
    # Convert the cron dict to a cron string
    cron_string = f"{cron.get('minute', '*')} {cron.get('hour', '*')} {cron.get('day', '*')} {cron.get('month', '*')} {cron.get('day_of_week', '*')}"
    
    # Create a croniter object
    cron_iter = croniter(cron_string, datetime.now())
    
    # Get the next two occurrences
    next_occurrence = cron_iter.get_next(datetime)
    second_occurrence = cron_iter.get_next(datetime)
    
    # Check if the difference is at least one minute
    return (second_occurrence - next_occurrence) >= timedelta(minutes=1)

def get_cron_and_timezone(description: str) -> Tuple[dict, Optional[str]]:
    if not description.strip():
        return {'date': datetime.now() + timedelta(seconds=5)}, None

    system_content = (
        "You are a helpful assistant skilled in converting English descriptions of schedules into "
        "cron strings and identifying timezones. Ensure that the resulting schedule does not run "
        "more frequently than once per minute."
    )

    user_content = (
        f"Convert the following English description into a JSON object with two keys:\n"
        f"1. 'cron': An object containing cron schedule parameters (minute, hour, day, "
        f"month, day_of_week, year) as needed. Use '*' for any field that should run every time. "
        f"DO NOT include a 'second' field. Ensure the job doesn't run more frequently than once per minute.\n"
        f"2. 'timezone': The timezone mentioned in the description. Use ONLY standard IANA "
        f"timezone names (e.g., 'America/New_York', 'Europe/London', 'Asia/Tokyo'). Do NOT use "
        f"abbreviations like EST, PST, etc. If no timezone is specified or if an invalid timezone "
        f"is given, set this to null.\n\n"
        f"English description: '{description}'\n\n"
        f"Ensure all cron fields are strings, even if they're numbers. For the timezone, use ONLY "
        f"standard IANA timezone names or null."
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]
    
    client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        response_format={"type": "json_object"},
    )
    
    result = json.loads(response.choices[0].message.content)
    logger.debug(f"Parsed schedule: {result}")
    
    cron = result['cron']
    timezone = result['timezone']

    logger.info(f"Generated cron: {cron}")
    logger.info(f"Generated timezone: {timezone}")

    # Remove 'second' field if it's present
    if 'second' in cron:
        del cron['second']
        logger.warn("Removed 'second' field from cron string")

    # Check if the cron would run more frequently than every 60 seconds
    if not is_valid_cron_frequency(cron):
        raise ValueError("Schedule must not run more frequently than once per minute.")

    if timezone == 'EST':
        timezone = 'America/New_York'
    return cron, timezone

class DailyLimitJobWrapper:
    """
    A wrapper class for scheduled jobs that enforces a maximum number of executions per day.

    This class wraps an asynchronous function (job) and ensures it's not executed more than
    a specified number of times per day. The day is defined according to the job's timezone.

    Attributes:
        func (Coroutine): The asynchronous function to be executed.
        max_runs_per_day (int): The maximum number of times the job can run per day.
        run_count (int): The current number of runs for the current day.
        last_reset (datetime): The date when the run count was last reset, in the job's timezone.
        timezone (tzinfo): The timezone in which the job is scheduled.

    Methods:
        wrapped_func(): Returns a coroutine that enforces the daily limit before executing the wrapped function.
    """

    def __init__(self, func, max_runs_per_day: int, timezone: pytz.tzinfo.BaseTzInfo):
        """
        Initialize the DailyLimitJobWrapper.

        Args:
            func (Coroutine): The asynchronous function to be wrapped and executed.
            max_runs_per_day (int): The maximum number of times the job can run per day.
            timezone (pytz.tzinfo.BaseTzInfo): The timezone in which the job is scheduled.
        """
        self.func             = func
        self.max_runs_per_day = max_runs_per_day
        self.run_count        = 0
        self.timezone         = timezone
        self.last_reset       = datetime.now(self.timezone).date()

    def wrapped_func(self):
        """
        Return a coroutine that enforces the daily limit before executing the wrapped function.

        This method creates and returns a new coroutine that checks the daily limit,
        increments the count if the limit hasn't been reached, and then executes the
        wrapped function.

        Returns:
            Coroutine: A coroutine that will execute the wrapped function if the daily limit allows.
        """
        @wraps(self.func)
        async def wrapper(*args, **kwargs):
            if self._should_reset():
                self._reset_count()

            if self.run_count < self.max_runs_per_day:
                self.run_count += 1
                logger.info(f"Running job. Run count for today: {self.run_count}/{self.max_runs_per_day}")
                return await self.func(*args, **kwargs)
            else:
                logger.warn(f"Daily run limit reached. Skipping job execution.")

        return wrapper

    def _should_reset(self) -> bool:
        """
        Check if the run count should be reset based on the current date.

        Returns:
            bool: True if the current date is different from the last reset date, False otherwise.
        """
        current_date = datetime.now(self.timezone).date()
        return current_date > self.last_reset

    def _reset_count(self):
        """
        Reset the run count and update the last reset date.
        """
        self.run_count = 0
        self.last_reset = datetime.now(self.timezone).date()
        logger.info(f"Reset daily run count. New date: {self.last_reset}")

    def get_run_count(self):
        """
        Get the current run count for the job.

        Returns:
            int: The number of times the job has run today.
        """
        if self._should_reset():
            self._reset_count()
        return self.run_count


def schedule_job(schedule:         str,
                 job_task:         Coroutine,
                 job_name:         str,
                 max_runs_per_day: int = 10):
    """
    Schedule a new job with the global scheduler.

    This function interprets a schedule description, creates a new job with the
    specified task and schedule, and adds it to the global scheduler. It enforces
    a minimum interval of 60 seconds between job runs.

    Args:
        schedule         (str): A natural language description of the job schedule,
                                potentially including a timezone.
        job_task         (Coroutine): The asynchronous function to be executed when the job runs.
        job_name         (str): A name for the job, used for identification.
        max_runs_per_day (int): Maximum number of times the job can run per day.


    Returns:
        Job: The scheduled job object, which can be used to modify or remove the job later.

    Raises:
        ValueError: If the schedule would result in the job running more frequently than every 60 seconds.
    """
    global scheduler, job_wrappers
    try:
        cron_or_date, timezone = get_cron_and_timezone(schedule)
    except ValueError as e:
        logger.warn(f"Invalid schedule for job '{job_name}': {e}")
        raise

    logger.debug(f"Cron or date is: {cron_or_date}")
    logger.debug(f"Timezone is: {timezone}")

    if timezone:
        try:
            tz = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            logger.warn(f"Unknown time zone: {timezone}. Using UTC.")
            tz = pytz.UTC
    else:
        tz = pytz.UTC

    # Wrap the job_task with DailyLimitJobWrapper
    wrapper = DailyLimitJobWrapper(job_task, max_runs_per_day, tz)
    wrapped_job = wrapper.wrapped_func()
    
    # Store the wrapper instance
    job_wrappers[job_name] = wrapper

    if isinstance(cron_or_date, dict) and 'date' in cron_or_date:
        # This is a one-time job
        logger.info(f"Scheduling one-time job '{job_name}' for date: {cron_or_date['date']}")
        job = scheduler.add_job(
            wrapped_job,
            trigger='date',
            run_date=cron_or_date['date'],
            name=job_name,
            timezone=tz
        )
    else:
        # This is a recurring job
        logger.info(f"Scheduling recurring job '{job_name}' with cron: {cron_or_date}")
        job = scheduler.add_job(
            wrapped_job,
            trigger='cron',
            name=job_name,
            timezone=tz,
            **cron_or_date
        )
    logger.info(f"Job '{job_name}' scheduled with max {max_runs_per_day} runs per day in {tz}. Next run time: {job.next_run_time}")

    return job



######################################################################################################
# Triggerable class 
#
class ScheduleTriggerable(Triggerable):
    """
    A triggerable class for scheduling and managing recurring or one-time jobs.

    This class extends the Triggerable superclass to handle schedule-based triggers.
    It integrates with a scheduler (assumed to be APScheduler) to manage job execution
    based on specified schedules.

    Attributes:
        SCHEDULER_RUNNING (bool): Class variable to track if the scheduler has been started.
        max_runs_per_day (int): Maximum number of times a job can run per day.

    Inherited Attributes:
        agent_id (str): The ID of the agent associated with this triggerable.
        agent_name (str): The name of the agent.
        agent_slug (str): A slug identifier for the agent.
        tenant_id (str): The ID of the tenant this triggerable belongs to.
        user_id (str): The ID of the user who owns this triggerable.
        trigger (str): The type of trigger (always starts with "Scheduler" for this class).
        trigger_arg (str): Arguments for the trigger, typically a schedule description.
        run_state: An object to manage the running state of the triggerable.

    Methods:
        handles_trigger(cls, trigger: str) -> bool:
            Class method to check if this class can handle a given trigger type.
        
        run() -> None:
            Asynchronous method to start and manage the scheduled job.
        
        run_job() -> None:
            Asynchronous method that defines the actual job to be run on schedule.
        
        cancel() -> None:
            Asynchronous method to cancel the scheduled job.
        
        pick_credential(credentials) -> bool:
            Method to select appropriate credentials for the job (if needed).
    """

    SCHEDULER_RUNNING = False
    
    def __init__(self, agent_dict: dict, run_state) -> None:
        """
        Initialize the ScheduleTriggerable.

        Args:
            agent_dict (dict): A dictionary containing agent and trigger information.
            run_state: An object to manage the running state of the triggerable.
        """
        super().__init__(agent_dict, run_state)
        #self.max_runs_per_day = agent_dict.get('max_runs_per_day', 10)  # Default to 10 if not specified
        self.max_runs_per_day = 10
        
    @classmethod
    def handles_trigger(cls, trigger: str) -> bool:
        """
        Check if this class can handle the given trigger type.

        Args:
            trigger (str): The trigger type to check.

        Returns:
            bool: True if the trigger starts with "Scheduler", False otherwise.
        """
        return trigger.startswith("Scheduler")

    async def run(self):
        """
        Start and manage the scheduled job.

        This method initializes the scheduler if it's not already running,
        schedules the job based on the trigger arguments, and manages its lifecycle.
        """
        if not ScheduleTriggerable.SCHEDULER_RUNNING:
            ScheduleTriggerable.SCHEDULER_RUNNING = True
            scheduler_start()
        logger.debug("Creating schedule trigger")
        try:
            self.job = schedule_job(self.trigger_arg,
                                    self.run_job,
                                    self.agent_name,
                                    self.max_runs_per_day)
            while await self.run_state.is_running():
                await asyncio.sleep(0.5)
            self.job.remove()
            logger.debug("Quitting Schedule trigger")
        except Exception as e:
            logger.error(f"Error starting schedule trigger: {e}")

    async def run_job(self):
        """
        Define the job to be run on schedule.

        This method is called by the scheduler when it's time to run the job.
        It logs the execution and calls the create_run method to start the agent.
        """
        logger.debug(f"Invoking scheduled job: {self.agent_name}")
        self.create_run('run your instructions')

    async def cancel(self):
        """
        Cancel the scheduled job.

        This method is called when the job needs to be cancelled. It removes
        the job from the scheduler.
        """
        logger.debug(f"Invoking cancel job: {self.agent_name}")
        self.job.remove()

    def pick_credential(self, credentials) -> bool:
        """
        Select appropriate credentials for the job.

        This method is a placeholder and currently always returns True.
        It can be overridden to implement credential selection logic if needed.

        Args:
            credentials: The available credentials (type depends on implementation).

        Returns:
            bool: Always returns True in this implementation.
        """
        return True


