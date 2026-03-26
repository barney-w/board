using './main.bicep'

param developerName = readEnvironmentVariable('DEV_NAME', 'jbloggs')
param adminSshPublicKey = readEnvironmentVariable('SSH_PUB_KEY')
