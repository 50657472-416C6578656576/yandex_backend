# yandex_backend
Yandex backend-school entry task.

- [Task](https://github.com/50657472-416C6578656576/yandex_backend/blob/master/enrollment/Task.md) and [openAPI specifications](https://github.com/50657472-416C6578656576/yandex_backend/blob/master/enrollment/openapi.yaml) are in the `enrollment` directory.
- My realization is in the `PROJECT` directory.

---

### To install the required dependencies go to the `PROJECT` directory and type:
```bash
$ pip install -e .
```


### To run the application go to the `market` directory and type:
```bash
$ export FLASK_APP=app
$ python3 -m flask run -h <HOST> -p <PORT>
```


### Unfortunately, you need to initialize the DataBase and tables in there by your self:
```bash
$ python3
>>> from app import db
>>> db.create_all()
```
