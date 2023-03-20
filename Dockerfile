FROM python:3.10
WORKDIR /usr/src/
ADD . ibl-to-nwb/
RUN cd ibl-to-nwb \
  && pip install -e .[brainwide_map]
