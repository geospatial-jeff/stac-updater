# stac-updater
CLI for building and deploying an AWS service designed to update and maintain STAC (via Lambda/SNS/SQS).  

# Installation
```
git clone https://github.com/geospatial-jeff/stac-updater
cd stac-updater
python setup.py develop
```

# Usage
Use the [stac-updater CLI](stac_updater/cli.py) to build and deploy your service.  Updating a static collection, for example, is accomplished as follows:

```
# Start a new service
stac-updater new-service

# Build AWS resources to update collection
stac-updater update-collection --name landsat-8-l1 --root https://stac.com/landsat-8-l1/catalog.json

# Modify kickoff event source to s3:ObjectCreated
stac-updater modify-kickoff --type s3 --bucket_name stac-updater-kickoff

# Deploy the service to AWS
stac-updater deploy
```

Once deployed, any STAC Item uploaded to the `stac-updater-kickoff` bucket will be ingested by the service and added to the `https://stac.com/landsat-8-l1/catalog.json` collection.
