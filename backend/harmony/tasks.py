from harmony import celery
from harmony.analyzer import Analyzer


@celery.task
def start_analysis_task(channel_id):
    Analyzer(channel_id).start_analysis()


@celery.task
def stop_analysis_task(channel_id):
    Analyzer(channel_id).stop_analysis()


'''
the way analysis will work is
start analysis for specific channel
starting analysis will start the stage the channel is currently at
once analysis is done for the current stage, analysis will pause
analysis for the next stage must be started again by calling start analysis again
analysis can be stopped at any time with stop_analysis
if analysis is stopped, the progress for the current stage will be reset and that stage will have to be restarted
progress can be gotten at any time using the progress route which will show the current stage and progress for the stage and whether its been completed or not
the frontned will have auto option that automatically continues after it sees stage has been finished???

frontend will have user alternates filled out
frontend posts those alternates to backend
backend populates database with alternates
later the backend will utilize those alternates when doing entity sentiments for each user

to check if a stage was completed/vs stopped by user, check the value of running and progress
if running is False and progress is 0, the previous stage was completed and the current stage has not yet been run
if running is False and progress is not 0, the current stage was run but not completed, therefore it must be restarted and the tables must be cleared

first the frontend sets the limit
then gathering messages starts
then user sets alternates
then create clusters starts
then coref starts
then sentiment starts
then the end

call start
call limit
call start
call start
call alternates
call start
call start
call start
the end
'''