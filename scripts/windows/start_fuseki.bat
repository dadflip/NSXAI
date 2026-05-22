@echo off
set FUSEKI_BASE=C:\Users\david\Documents\Github\NSXAI\triplestore\apache-jena-fuseki-5.1.0\run
echo Fuseki : http://localhost:3030
echo Dataset : nsxai
cd /d "C:\Users\david\Documents\Github\NSXAI\triplestore\apache-jena-fuseki-5.1.0"
call "C:\Users\david\Documents\Github\NSXAI\triplestore\apache-jena-fuseki-5.1.0\fuseki-server.bat"
