FROM grafana/grafana:12.4.0
USER root
# demo shell: show the platform name instead of "Grafana" (in Peresvet this is Enterprise white labeling)
RUN f=$(grep -l 'static{this.AppTitle="Grafana"}' /usr/share/grafana/public/build/*.js) && \
    sed -i 's/static{this.AppTitle="Grafana"}/static{this.AppTitle="МПК-Пересвет"}/' $f
COPY plugins /var/lib/grafana/plugins
COPY provisioning /etc/grafana/provisioning
COPY dashboards /var/lib/grafana/dashboards
RUN mkdir -p /var/lib/grafana/data && chown -R 472:0 /var/lib/grafana
USER 472
