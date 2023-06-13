# URL Shortening App

## Getting Started

### Prerequisites

Run the following command to install the required packages:

```bash
python -m pip install -r requirements.txt
```

### Usage

Create a `.env.local` file similar to `.env.example` and fill in the values. Then, start the application 
by running the following command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

The documentation for the API can be found at [http://localhost:8090/docs](http://localhost:8090/docs).

## Deployment

### Docker

In order to run the application using Docker, you need to build the image first:

```bash
docker build -t benhid/url_shortening_app:1.0.2 .
```

Then, run the container pointing to the `.env.local` file:

```bash
docker run --rm --env-file ./.env.local -p 8090:8090 benhid/url_shortening_app:1.0.2
```

### Kubernetes

You can also run the application using Kubernetes. First, create a namespace:

```bash
kubectl create namespace my-app
```

Then, create a secret with the `.env.local` file:

```bash
kubectl create secret generic -n my-app url-shortening-app-env --from-env-file=./.env.local
```

Finally, deploy the application:

```bash
$ kubectl apply -f manifests/deployment.yaml
$ kubectl apply -f manifests/service.yaml
```

(or use `kubectl apply -f manifests` to apply all the manifests at once)

> The deployment uses the image `benhid/url_shortening_app:1.0.2` by default. If you want to use a different image,
> replace the value of the `image` field in the `manifests/deployment.yaml` file.

Your application should now be accessible at `http://<node-ip>:<node-port>`.

To check the node port, run the following command and look for the `PORT(s)` value:

```bash
kubectl get svc -n my-app
```

## Testing

To test the API, you can use the following commands (replace `<api-key>` and `<digest>` with the values returned by the previous commands):

```bash
$ curl -X 'POST' 'http://0.0.0.0:8000/api/v1/issue/api_key?expires_in_seconds=3600'
$ curl -X 'POST' 'http://0.0.0.0:8000/api/v1/shorten?ttl=120' \
      -H 'accept: application/json' \
      -H 'Content-Type: application/json' \
      -H 'X-Api-key: <api-key>' \
      -d '{
        "url": "https://www.google.com"
      }'
$ curl -X 'GET' -I 'http://0.0.0.0:8000/r/<digest>'
```

## License

This project is licensed under the terms of the MIT license. See [LICENSE](LICENSE) for more details.
