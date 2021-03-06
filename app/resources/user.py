from flask_restplus import Resource, fields
from flask import request
from app import app, db_engine, api
from sqlalchemy import text
import jwt
from time import time
import requests
import json
from uuid import uuid4


ns = api.namespace('user', description="유저 관련 API (Facebook/Kakao 로그인)")
user_post_payload = api.model('User_Post_Payload', {
    'accessToken': fields.String("Facebook/Kakao Access Token")
})


@ns.route('')
class User(Resource):
    @ns.param("type", "동작 종류 (현재는 'facebook' 만 가능)", _in="query", required=True)
    @ns.doc(body=user_post_payload)
    @ns.response(200, "로그인 성공 시 JsonWebToken 반환")
    def post(self):
        if 'type' not in request.args:
            return {"message": "Argument 'type' must be provided!"}, 400

        body = request.get_json(silent=True, force=True)
        if body is None:
            return {"message": "Unable to get json post data!"}, 400

        if request.args['type'] == 'kakao':
            if 'accessToken' not in body:
                return {"message": "'accessToken' not provided!"}, 400

            kakao_access_token = body['accessToken']

            headers = {"Authorization": "Bearer " + kakao_access_token}
            res = requests.get("https://kapi.kakao.com/v1/user/me", headers=headers)
            status_code = res.status_code
            content = json.loads(res.text)

            if not res.ok:
                return {"message": content['msg']}, status_code

            kakao_id = int(content['id'])

            with db_engine.connect() as connection:
                query_str = "SELECT * FROM `users` WHERE `kakao_id` = :kakao_id"
                chk_user = connection.execute(text(query_str), kakao_id=kakao_id).first()

                if chk_user is None:
                    with connection.begin() as transaction:
                        query_str = "INSERT INTO `users` SET `name` = :name, `kakao_id` = :kakao_id"
                        query = connection.execute(text(query_str),
                                                   name=content['properties']['nickname'], kakao_id=kakao_id)

                    query_str = "SELECT * FROM `users` WHERE `kakao_id` = :kakao_id"
                    chk_user = connection.execute(text(query_str), kakao_id=kakao_id).first()

                if int(chk_user['enabled']) != 1:
                    return {"message": "This account has been disabled. Please contact system administrator!"}

                auth_uuid = str(uuid4())
                with connection.begin() as transaction:
                    query_str = "UPDATE `users` SET `auth_uuid` = :auth_uuid, `name` = :name WHERE `id` = :user_id"
                    query = connection.execute(text(query_str),
                                               auth_uuid=auth_uuid,
                                               name=content['properties']['nickname'],
                                               user_id=chk_user['id'])

            return {
                "jwt": jwt.encode({
                    'user_id': chk_user['id'],
                    'user_name': chk_user['name'],
                    'auth_uuid': auth_uuid,
                    'exp': int(time()) + 86400
                }, key=app.config['JWT_SECRET_KEY'], algorithm='HS512').decode('utf-8')
            }, 200

        elif request.args['type'] == 'facebook':
            if 'accessToken' not in body:
                return {"message": "'accessToken' not provided!"}, 400

            fb_access_token = body['accessToken']

            params = {"access_token": fb_access_token, "fields": "id,name"}
            res = requests.get("https://graph.facebook.com/v2.9/me", params=params)
            status_code = res.status_code
            content = json.loads(res.text)

            if not res.ok:
                return content['error'], status_code

            fb_id = int(content['id'])

            with db_engine.connect() as connection:
                query_str = "SELECT * FROM `users` WHERE `fb_id` = :fb_id"
                chk_user = connection.execute(text(query_str), fb_id=fb_id).first()

                if chk_user is None:
                    with connection.begin() as transaction:
                        query_str = "INSERT INTO `users` SET `name` = :name, `fb_id` = :fb_id"
                        query = connection.execute(text(query_str), name=content['name'], fb_id=fb_id)

                    query_str = "SELECT * FROM `users` WHERE `fb_id` = :fb_id"
                    chk_user = connection.execute(text(query_str), fb_id=fb_id).first()

                if int(chk_user['enabled']) != 1:
                    return {"message": "This account has been disabled. Please contact system administrator!"}

                auth_uuid = str(uuid4())
                with connection.begin() as transaction:
                    query_str = "UPDATE `users` SET `auth_uuid` = :auth_uuid, `name` = :name WHERE `id` = :user_id"
                    query = connection.execute(text(query_str),
                                               auth_uuid=auth_uuid,
                                               name=content['name'],
                                               user_id=chk_user['id'])

            return {
                "jwt": jwt.encode({
                    'user_id': chk_user['id'],
                    'user_name': chk_user['name'],
                    'auth_uuid': auth_uuid,
                    'exp': int(time()) + 86400
                }, key=app.config['JWT_SECRET_KEY'], algorithm='HS512').decode('utf-8')
            }, 200
        else:
            return {"message": "Invalid 'type' given!"}, 400
