from __future__ import annotations
import os
from datetime import datetime, timedelta
from flask import Flask, request
from flask_api import status
from flask_sqlalchemy import SQLAlchemy
from validation_scripts import iso_validation, uuid_validation, unit_fields_validation, import_req_validation


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.abspath(os.getcwd()) + '\database.db'
db = SQLAlchemy(app, engine_options={'connect_args': {'check_same_thread': False}})


class AbstractShopUnit(db.Model):
    __abstract__ = True

    id = db.Column(db.String(36), primary_key=True)
    parent_id = db.Column(db.String(36))
    name = db.Column(db.String, nullable=False)
    is_category = db.Column(db.Boolean, nullable=False)
    price = db.Column(db.Integer)
    updated_at = None
    num_children = db.Column(db.Integer)

    # getters
    def get_price(self) -> int | None:
        if self.is_category:
            return int(self.price / self.num_children) if (self.num_children and self.price) else None
        else:
            return self.price

    def get_num_children(self) -> int:
        return self.num_children if self.is_category else 1

    def get_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'date': self.updated_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            'parentId': self.parent_id,
            'type': 'CATEGORY' if self.is_category else 'OFFER',
            'price': self.get_price(),
        }

    # defaults
    def __repr__(self, addition: str = '') -> str:
        return f'\n<{addition}ShopUnit-{"CATEGORY" if self.is_category else "OFFER"}, name={self.name}, ' \
               f'price={self.price}, {self.updated_at}, id={self.id}, parent={self.parent_id}, n_C={self.num_children}>'


class ShopUnit(AbstractShopUnit):
    updated_at = db.Column(db.DateTime, nullable=False)

    # adders
    def price_add(self, addendum: int):
        if self.price is None:
            self.price = addendum
        else:
            self.price += addendum

    # getters
    def get_children(self) -> list | None:
        if not self.is_category:
            return None
        children = ShopUnit.query.filter_by(parent_id=self.id).all()
        return [unit.get_dict() for unit in children]

    def get_dict(self) -> dict:
        res = super(ShopUnit, self).get_dict()
        res['children'] = self.get_children()
        return res

    # updaters
    def update_time(self, time: datetime) -> set:
        self.updated_at = time
        parent_ids = set()
        cur_id = self.parent_id
        while unit := ShopUnit.query.get(cur_id):
            parent_ids.add(cur_id)
            unit.updated_at = time
            cur_id = unit.parent_id
        return parent_ids

    def update_price(self, price: int):
        if (not self.is_category) and (diff := (price - self.price)):
            cur_id = self.parent_id
            while unit := ShopUnit.query.get(cur_id):
                unit.price += diff
                cur_id = unit.parent_id

    def update_parent(self, parent_id):
        total_price = self.price if self.price else 0
        # update info in old parents
        if self.parent_id != parent_id:
            self.delete_preparation(self.get_num_children(), total_price)
        # update info in new parents
        cur_id = parent_id
        while unit := ShopUnit.query.get(cur_id):
            unit.num_children += self.get_num_children()
            unit.price_add(total_price)
            cur_id = unit.parent_id
        self.parent_id = parent_id

    # delete methods
    def delete_preparation(self, num: int, total_price: int):
        cur_id = self.parent_id
        while unit := ShopUnit.query.get(cur_id):
            unit.num_children -= num
            unit.price_add(-total_price)
            cur_id = unit.parent_id

    def full_delete(self) -> (int, int):
        counter = 1
        full_price = self.price
        ids_to_del = {self.id}      # is used to delete history
        if self.is_category:        # delete the whole tree
            full_price = 0
            ids_q = [self.id]
            while ids_q:
                children = ShopUnit.query.filter(ShopUnit.parent_id.in_(ids_q))
                ids_q = []
                for u in children.all():
                    ids_to_del.add(u.id)
                    if u.is_category:
                        ids_q.append(u.id)
                    else:
                        full_price += u.price
                        counter += 1
                children.delete()

        self.delete_preparation(counter, full_price)
        OldShopUnit.delete_all(ids_to_del)
        db.session.delete(self)
        db.session.commit()
        return counter, full_price

    # defaults
    def __init__(self, **kwargs):
        self.num_children = 0
        super(ShopUnit, self).__init__(**kwargs)


class OldShopUnit(AbstractShopUnit):
    # Primary key: (id, updated_at)
    updated_at = db.Column(db.DateTime, primary_key=True)

    # static methods
    @staticmethod
    def add_all(id_set: set | list):
        copies = [OldShopUnit(u) for u in ShopUnit.query.filter(ShopUnit.id.in_(id_set)).all()]
        db.session.add_all(copies)

    @staticmethod
    def delete_all(id_set: set | list):
        OldShopUnit.query.filter(OldShopUnit.id.in_(id_set)).delete()

    # defaults
    def __repr__(self) -> str:
        return super(OldShopUnit, self).__repr__(addition='Old')

    def __init__(self, shop_unit: ShopUnit):
        super(OldShopUnit, self).__init__(id=shop_unit.id, name=shop_unit.name, price=shop_unit.price,
                                          is_category=shop_unit.is_category, updated_at=shop_unit.updated_at,
                                          parent_id=shop_unit.parent_id, num_children=shop_unit.num_children)


@app.post("/imports")
def import_shop_unit():
    used_ids, to_add_ids = set(), set()
    data = request.get_json()
    bad_request_response = {"code": 400,  "message": "Validation Failed"}, status.HTTP_400_BAD_REQUEST

    # data and date-format validation
    if (not import_req_validation(data)) or not (updated_at := iso_validation(data['updateDate'])):
        return bad_request_response

    for item in data['items']:
        # unique id per request validation
        if (not unit_fields_validation(item)) or (item['id'] in used_ids):
            return bad_request_response
        else:
            used_ids.add(item['id'])

        # parent validation
        if (item['parentId'] is not None) and ((not (parent_unit := ShopUnit.query.get(item['parentId'])))
                                               or parent_unit.is_category is not True):
            return bad_request_response

        if existing_unit := ShopUnit.query.get(item['id']):
            # switching type validation
            if (item['type'] == 'CATEGORY') != existing_unit.is_category:
                return bad_request_response
            # updating existing unit
            existing_unit.name = item['name']
            existing_unit.update_price(item['price'])
            to_add_ids = to_add_ids | existing_unit.update_time(updated_at)
            existing_unit.update_parent(item['parentId'])
            to_add_ids = to_add_ids | existing_unit.update_time(updated_at)
            to_add_ids.add(existing_unit.id)
        else:
            # creating new unit
            new_unit = ShopUnit(id=item['id'], name=item['name'], price=item['price'],
                                is_category=(item['type'] == 'CATEGORY'), updated_at=updated_at,
                                parent_id=item['parentId'])
            new_unit.update_parent(item['parentId'])
            to_add_ids = to_add_ids | new_unit.update_time(updated_at)
            to_add_ids.add(new_unit.id)
            db.session.add(new_unit)

    OldShopUnit.add_all(to_add_ids)
    db.session.commit()
    return {"code": 200, "message": "Success"}, status.HTTP_200_OK


@app.delete("/delete/<target_id>")
def delete_shop_unit(target_id: str):
    # input validation
    if not uuid_validation(target_id):
        return {"code": 400,  "message": "Validation Failed"}, status.HTTP_400_BAD_REQUEST
    # unit existence validation
    if not (target := ShopUnit.query.get(target_id)):
        return {"code": 404, "message": "ShopUnit Not Found"}, status.HTTP_404_NOT_FOUND

    target.full_delete()
    return {"code": 200, "message": "Success"}, status.HTTP_200_OK


@app.get("/nodes/<target_id>")
def get_nodes(target_id: str):
    # input validation
    if not uuid_validation(target_id):
        return {"code": 400,  "message": "Validation Failed"}, status.HTTP_400_BAD_REQUEST
    # unit existence validation
    if not (target := ShopUnit.query.get(target_id)):
        return {"code": 404, "message": "ShopUnit Not Found"}, status.HTTP_404_NOT_FOUND

    return target.get_dict(), status.HTTP_200_OK


@app.get("/sales")
def get_sales():
    if not (date := iso_validation(request.args.get('date'))):
        return {"code": 400,  "message": "Validation Failed"}, status.HTTP_400_BAD_REQUEST

    lo_date = date - timedelta(days=1)
    query = OldShopUnit.query.filter(lo_date <= OldShopUnit.updated_at, OldShopUnit.updated_at <= date)
    ans = [u.get_dict() for u in query.all()]

    return {'items': ans}, status.HTTP_200_OK


@app.get("/node/<target_id>/statistic")
def get_statistics(target_id: str):
    start_date = iso_validation(request.args.get('dateStart'))
    end_date = iso_validation(request.args.get('dateStart'))

    if (not uuid_validation(target_id)) or (not start_date) or (not end_date):
        return {"code": 400,  "message": "Validation Failed"}, status.HTTP_400_BAD_REQUEST
    if not ShopUnit.query.get(target_id):
        return {"code": 404, "message": "ShopUnit Not Found"}, status.HTTP_404_NOT_FOUND

    query = OldShopUnit.query.filter(OldShopUnit.id == target_id, start_date <= OldShopUnit.updated_at,
                                     OldShopUnit.updated_at < end_date)
    ans = [u.get_dict() for u in query.all()]

    return {'items': ans}, status.HTTP_200_OK
