from flask_restplus import Resource, fields
from flask import request
from app import db_engine, api
from sqlalchemy import text
from app.modules.pagination import Pagination
import app.modules.helper as helper
import json

ns = api.namespace('group', description="그룹 관련 API (목록 조회, 새로 생성)")
group_post_payload = api.model('Group_Post_Payload', {
    'name': fields.String("새로 생성할 그룹 이름 (중복 가능)"),
})
group_get_success = api.model('Group_Get_Success', {
    "list": fields.List(fields.Raw({
        "id": "그룹 고유번호",
        "name": "그룹 이름",
        "creator_id": "그룹 생성한 유저 고유번호",
        "role": "이 그룹에서 현재 유저가 가진 권한 (0: 일반 유저, 1: 중간 관리자, 2: 최고 관리자)",
        "created_at": "생성일자, Datetime ISO Format으로 주어짐"
    })),
    "pagination": fields.List(fields.Raw({
        'num': "pagination 번호",
        'text': 'pagination 단추에서 표시할 텍스트',
        'current': "현재 선택된 page면 true, 아닐 경우 false"
    }))
})
group_put_payload = api.model('Group_Put_Payload', {
    'signup_code': fields.String("그룹 가입 인증 코드 (최대길이 64, null일 경우 신규회원을 받지 않는 상태)")
})


@ns.route('')
@ns.param("jwt", "로그인 시 얻은 JWT를 입력", _in="query", required=True)
class Group(Resource):
    @ns.response(200, "그룹 목록", model=group_get_success, as_list=True)
    def get(self):
        if request.user_info is None:
            return {"message": "JWT must be provided!"}, 401

        page = 1
        if 'page' in request.args:
            page = int(request.args['page'])

        with db_engine.connect() as connection:
            fetch_query = " SELECT `groups`.`id`, `groups`.`name`, `groups`.`creator_id`, `members`.`role`, " \
                          "`groups`.`signup_code`, `groups`.`created_at` FROM `groups` " \
                          "JOIN `members` ON `groups`.`id` = `members`.`group_id` " \
                          "WHERE `members`.`user_id` = :user_id AND `groups`.`is_enabled` = 1 "
            count_query = "SELECT COUNT(`groups`.`id`) AS `cnt` FROM `groups` " \
                          "JOIN `members` ON `groups`.`id` = `members`.`group_id` " \
                          "WHERE `members`.`user_id` = :user_id "
            order_query = " ORDER BY `groups`.`id` ASC "

            result, paging = Pagination(fetch=fetch_query,
                                        count=count_query,
                                        order=order_query,
                                        current_page=page,
                                        connection=connection,
                                        fetch_params={'user_id': request.user_info['id']}).get_result()

        return json.loads(str(json.dumps({
            'list': result,
            'pagination': paging
        }, default=helper.json_serial))), 200

    @ns.doc(body=group_post_payload)
    @ns.response(201, "새 그룹을 성공적으로 생성함")
    def post(self):
        if request.user_info is None:
            return {"message": "JWT must be provided!"}, 401

        body = request.get_json(silent=True, force=True)
        if body is None:
            return {"message": "Unable to get json post data!"}, 400

        if 'name' not in body:
            return {"message": "'name' not provided!"}, 400

        if len(body['name']) > 64:
            return {"message": "Length of 'name' must be smaller than 64!"}, 400

        with db_engine.connect() as connection:
            with connection.begin() as transaction:
                query_str = "INSERT INTO `groups` SET `name` = :name, `creator_id` = :user_id"
                query = connection.execute(text(query_str), name=body['name'], user_id=request.user_info['id'])

                new_group_id = query.lastrowid

                query_str = "INSERT INTO `members` SET `group_id` = :group_id, `user_id` = :user_id, `role` = '2'"
                query = connection.execute(text(query_str), group_id=new_group_id, user_id=request.user_info['id'])

        return {"group_id": new_group_id}, 201


@ns.route('/<int:group_id>')
@ns.param("jwt", "로그인 시 얻은 JWT를 입력", _in="query", required=True)
class GroupEach(Resource):
    @ns.doc(body=group_put_payload)
    @ns.response(200, "그룹 가입 정보 업데이트 성공")
    def put(self, group_id):
        if request.user_info is None:
            return {"message": "JWT must be provided!"}, 401

        body = request.get_json(silent=True, force=True)
        if body is None:
            return {"message": "Unable to get json post data!"}, 400

        signup_code = None
        if 'code' in body and body['code'] != "":
            signup_code = body['code']

        with db_engine.connect() as connection:
            query_str = "SELECT * FROM `groups` WHERE `id` = :group_id"
            chk_group = connection.execute(text(query_str), group_id=group_id).first()

            if chk_group is None:
                return {"message": "Requested 'group_id' not found!"}, 404

            if int(chk_group['creator_id']) != int(request.user_info['id']):
                return {"message": "Only creator of this group can update signup code!"}, 403

            with connection.begin() as transaction:
                query_str = "UPDATE `groups` SET `signup_code` = :signup_code WHERE `id` = :group_id"
                query = connection.execute(text(query_str), signup_code=signup_code, group_id=group_id)

        return {"group_id": group_id, "code": signup_code}, 201

    @ns.response(200, "해당 그룹을 성공적으로 비활성화함.")
    def delete(self, group_id):
        if request.user_info is None:
            return {"message": "JWT must be provided!"}, 401

        with db_engine.connect() as connection:
            query_str = "SELECT * FROM `groups` WHERE `id` = :group_id"
            chk_group = connection.execute(text(query_str), group_id=group_id).first()

            if chk_group is None:
                return {"message": "Requested 'group_id' not found!"}, 404

            if int(chk_group['creator_id']) != int(request.user_info['id']):
                return {"message": "Only creator of this group can delete it!"}, 403

            with connection.begin() as transaction:
                query_str = "UPDATE `groups` SET `is_enabled` = 0 WHERE `id` = :group_id"
                query = connection.execute(text(query_str), group_id=group_id)

                query_str = "DELETE FROM `members` WHERE `group_id` = :group_id"
                query = connection.execute(text(query_str), group_id=group_id)

        return {"group_id": group_id}, 200
