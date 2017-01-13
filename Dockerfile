FROM python:latest

RUN mkdir /code
COPY . /code
RUN pip install -r /code/requirements.txt

VOLUME /code
EXPOSE 8000

ENTRYPOINT ["python"]
CMD ["/code/app.py"]
