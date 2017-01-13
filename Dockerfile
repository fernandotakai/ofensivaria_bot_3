FROM python:latest

RUN mkdir /code
COPY . /code
WORKDIR /code
RUN pip install -r requirements.txt && pip install .

VOLUME /code
EXPOSE 8000

ENTRYPOINT ["python"]
CMD ["-m", "ofensivaria.app"]
