# stac-updater
CLI for building and deploying an AWS service designed to update and maintain STAC (via Lambda/SNS/SQS).  

# Installation
```
git clone https://github.com/geospatial-jeff/stac-updater
cd stac-updater
python setup.py develop
```

# Usage
Use the [stac-updater CLI](stac_updater/cli.py) to build and deploy your service.

## Update Static Collection
```
# Start a new service
stac-updater new-service

# Build AWS resources to update collection
stac-updater update-collection --root https://stac.com/landsat-8-l1/catalog.json

# Modify kickoff event source to s3:ObjectCreated
stac-updater modify-kickoff --type s3 --bucket_name stac-updater-kickoff

# Deploy the service to AWS
stac-updater deploy
```

Once deployed, any STAC Item uploaded to the `stac-updater-kickoff` bucket will be ingested by the service and added to the `https://stac.com/landsat-8-l1/catalog.json` collection.  Regardless of event source, the service expects the following JSON payload:

| Field Name | Type  | Description | Example |
| ---------- | ----- | ----------- | ------- |
| stac_item  | dict  | **REQUIRED.** [STAC Item](https://github.com/radiantearth/stac-spec/tree/master/item-spec) to ingest into collection. | [link](https://github.com/radiantearth/stac-spec/blob/dev/item-spec/examples/sample-full.json) |
| path  | str  | String pattern indicating subcatalogs.  Used by [sat-stac](https://github.com/sat-utils/sat-stac/blob/master/tutorial-1.ipynb#Views) to automatically build sub catalogs from item properties. | '${landsat:path}/${landsat:row}' |
| filename  | str  | String pattern indicating filename. Used by [sat-stac](https://github.com/sat-utils/sat-stac/blob/master/tutorial-1.ipynb#Views) to automatically build item filename from item properties.| '${date}/${id}' |

Each call to `update-collection` tells the services to update a single collection.  Updating multiple collections within a single deployment is accomplished with multiple calls to `update-collection`.  When updating multiple collections, the services uses a SNS fanout pattern to distribute messages across multiple queues (1 queue per collection).

![abc](docs/images/update-collection.png)

## SNS Notifications
You may additionally deploy a SNS topic which publishes messages whenever a STAC Item is succesfully uploaded to a collection.

```
# Add SNS notification
stac-updater add-notifications --topic_name stac-updater-notifications
```

Once deployed, end-users may subscribe to the newly created SNS topic to be notified when new items are added.  The SNS Topic supports filtering on bbox and collection through a SNS Filter Policy.  The following policy notifies a subscriber only when a new STAC Item is added to the `landsat-8-l1` catalog within a 1x1 degree bounding box.

```json
{
	"bbox.xmin": [{"numeric":[">=",-118]}],
	"bbox.ymin": [{"numeric":[">=",33]}],
	"bbox.xmax": [{"numeric":["<=",-117]}],
	"bbox.ymax": [{"numeric":["<=",34]}],
	"collection": ["landsat-8-l1"]
}
```

# TODOS
- Add support for dynamic catalogs ([sat-api](https://github.com/sat-utils/sat-api), [staccato](https://github.com/boundlessgeo/staccato)).
- Add aggregator service for metrics/logging etc.
